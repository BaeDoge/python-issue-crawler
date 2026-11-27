"""Deterministic checks for executable Python examples in generated notes."""

from __future__ import annotations

import ast
import builtins

from verify.code_blocks import iter_fenced_code_blocks


_IMPORT_HINTS = {
    "Any": "from typing import Any",
    "Callable": "from typing import Callable",
    "DefaultDict": "from typing import DefaultDict",
    "Deque": "from typing import Deque",
    "Dict": "from typing import Dict",
    "FrozenSet": "from typing import FrozenSet",
    "Iterable": "from typing import Iterable",
    "Iterator": "from typing import Iterator",
    "List": "from typing import List",
    "Mapping": "from typing import Mapping",
    "Optional": "from typing import Optional",
    "Sequence": "from typing import Sequence",
    "Set": "from typing import Set",
    "Tuple": "from typing import Tuple",
    "Union": "from typing import Union",
    "Counter": "from collections import Counter",
    "defaultdict": "from collections import defaultdict",
    "deque": "from collections import deque",
    "bisect": "import bisect",
    "bisect_left": "from bisect import bisect_left",
    "bisect_right": "from bisect import bisect_right",
    "insort": "from bisect import insort",
    "heapq": "import heapq",
    "heapify": "from heapq import heapify",
    "heappop": "from heapq import heappop",
    "heappush": "from heapq import heappush",
    "heappushpop": "from heapq import heappushpop",
    "nlargest": "from heapq import nlargest",
    "nsmallest": "from heapq import nsmallest",
    "combinations": "from itertools import combinations",
    "permutations": "from itertools import permutations",
    "product": "from itertools import product",
    "chain": "from itertools import chain",
    "accumulate": "from itertools import accumulate",
    "lru_cache": "from functools import lru_cache",
    "cache": "from functools import cache",
    "reduce": "from functools import reduce",
    "sqrt": "from math import sqrt",
    "gcd": "from math import gcd",
    "lcm": "from math import lcm",
    "ceil": "from math import ceil",
    "floor": "from math import floor",
    "factorial": "from math import factorial",
    "isqrt": "from math import isqrt",
    "log": "from math import log",
    "log2": "from math import log2",
    "log10": "from math import log10",
    "comb": "from math import comb",
    "perm": "from math import perm",
    "inf": "from math import inf",
    "collections": "import collections",
    "functools": "import functools",
    "itertools": "import itertools",
    "math": "import math",
    "operator": "import operator",
    "random": "import random",
    "re": "import re",
    "statistics": "import statistics",
    "string": "import string",
}


def _defined_names(tree: ast.AST) -> set[str]:
    """Collect names declared anywhere in a snippet, including imports and parameters."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".", 1)[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _loaded_names(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _is_placeholder_body(statements: list[ast.stmt]) -> bool:
    body = list(statements)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, (ast.Str, ast.Constant)):
        value = getattr(body[0].value, "value", getattr(body[0].value, "s", None))
        if isinstance(value, str):
            body.pop(0)
    if len(body) != 1:
        return False
    statement = body[0]
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and statement.value.value is Ellipsis:
        return True
    if isinstance(statement, ast.Raise):
        exception = statement.exc
        if isinstance(exception, ast.Name):
            return exception.id == "NotImplementedError"
        if isinstance(exception, ast.Call):
            return isinstance(exception.func, ast.Name) and exception.func.id == "NotImplementedError"
    return False


def _has_placeholder_function(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_placeholder_body(node.body):
            return True
    return False


def validate_python_code_blocks(text: str) -> list[str]:
    """Check syntax, placeholder functions, and common missing imports in Python fences.

    This deliberately does not attempt full undefined-name analysis: LeetCode supplies
    common node types such as TreeNode/ListNode, and solution snippets may reference
    those platform-provided types without defining them locally.
    """
    issues: list[str] = []
    builtins_set = set(dir(builtins))
    for index, block in enumerate(iter_fenced_code_blocks(text or ""), 1):
        if not block.complete:
            issues.append(f"코드 블록 {index}: 닫히지 않은 코드 펜스가 있습니다.")
            continue
        if block.language not in {"python", "py", "python3"}:
            continue
        try:
            tree = ast.parse(block.body)
        except SyntaxError as exc:
            line = exc.lineno or 1
            message = (exc.msg or "SyntaxError").strip()
            issues.append(f"Python 코드 블록 {index}: 문법 오류({line}행, {message}). 복사 실행 가능한 코드로 수정할 것.")
            continue

        if _has_placeholder_function(tree):
            issues.append(f"Python 코드 블록 {index}: pass, ... 또는 NotImplementedError만 있는 미완성 함수가 있습니다.")
        missing = sorted(
            name
            for name in (_loaded_names(tree) & set(_IMPORT_HINTS))
            if name not in _defined_names(tree) and name not in builtins_set
        )
        if missing:
            hints = ", ".join(f"{name} ({_IMPORT_HINTS[name]})" for name in missing[:5])
            issues.append(f"Python 코드 블록 {index}: 필요한 import가 누락되었을 수 있습니다: {hints}. 각 코드 블록에 필요한 import를 포함할 것.")
    return issues


_NON_CODE_FENCE_LANGUAGES = {
    "text", "txt", "plain", "plaintext", "console", "output",
    "flow", "mermaid", "json", "yaml", "yml",
}


def validate_code_languages(
    text: str,
    *,
    allowed_languages: tuple[str, ...] = ("python", "py", "python3"),
    allowed_non_code_languages: set[str] | None = None,
) -> list[str]:
    """Reject unexpected programming-language fences in language-specific sections."""
    allowed = {language.casefold() for language in allowed_languages}
    non_code = allowed_non_code_languages or _NON_CODE_FENCE_LANGUAGES
    issues: list[str] = []
    for index, block in enumerate(iter_fenced_code_blocks(text or ""), 1):
        if not block.complete:
            continue
        language = block.language
        if not language:
            issues.append(
                f"코드 블록 {index}: 언어 정보가 없습니다. Python 코드라면 python 펜스를 지정하고, "
                "입출력 예시라면 text 펜스를 사용할 것."
            )
            continue
        if language in allowed or language in non_code:
            continue
        issues.append(
            f"코드 블록 {index}: {language} 언어 펜스가 있습니다. "
            f"이 섹션은 {', '.join(sorted(allowed))} 코드로 작성할 것."
        )
    return issues
