"""Execution-based checks for generated LeetCode solution snippets.

The runner is deliberately best-effort rather than a hostile-code OS sandbox:
it uses an isolated child interpreter, restricted builtins/imports, AST policy
checks, a temporary working directory, resource limits where available, and a
short timeout. Never use it as a replacement for a container/VM boundary when
executing arbitrary third-party code.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

from verify.code_blocks import iter_fenced_code_blocks


MANIFEST_MARKER = "ALGORITHM_TESTS"
MAX_MANIFEST_CHARS = 48_000
MAX_SOLUTION_CHARS = 28_000
MAX_CASES_PER_SOLUTION = 8
MIN_CASES_PER_SOLUTION = 3
MAX_SOLUTIONS = 2
RUN_TIMEOUT_SECONDS = 4

_ALLOWED_IMPORTS = {
    "array",
    "bisect",
    "collections",
    "copy",
    "decimal",
    "enum",
    "fractions",
    "functools",
    "heapq",
    "itertools",
    "math",
    "operator",
    "random",
    "re",
    "statistics",
    "string",
    "typing",
    "__future__",
}
_BLOCKED_CALLS = {
    "breakpoint",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
    "memoryview",
}
_ENTRYPOINT_RE = re.compile(r"^(?:Solution\.)?[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class AlgorithmSolutionSpec:
    section: str
    block_index: int
    entrypoint: str
    cases: tuple[dict[str, Any], ...]


def _manifest_match(raw: str):
    pattern = re.compile(
        r"<!--\s*" + re.escape(MANIFEST_MARKER) + r"\s*(\{[\s\S]*?\})\s*-->",
        re.IGNORECASE,
    )
    return pattern.search(raw or "")


def _is_json_value(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def parse_algorithm_test_manifest(
    raw: str,
    sections: dict[str, str],
) -> tuple[list[AlgorithmSolutionSpec], list[str]]:
    """Parse and validate the hidden JSON test manifest embedded in a draft."""
    match = _manifest_match(raw)
    if not match:
        return [], [
            "알고리즘 테스트 명세가 없습니다. 첫 섹션 헤더 앞에 ALGORITHM_TESTS JSON 주석을 추가할 것."
        ]
    payload = match.group(1)
    if len(payload) > MAX_MANIFEST_CHARS:
        return [], ["알고리즘 테스트 명세가 너무 큽니다. 테스트 케이스 수와 입력 크기를 줄일 것."]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return [], [f"알고리즘 테스트 명세 JSON 오류({exc.lineno}행): 올바른 JSON으로 수정할 것."]
    if not isinstance(data, dict) or not isinstance(data.get("solutions"), list):
        return [], ["알고리즘 테스트 명세는 solutions 배열을 포함하는 JSON 객체여야 합니다."]
    raw_solutions = data["solutions"]
    if not 1 <= len(raw_solutions) <= MAX_SOLUTIONS:
        return [], [f"테스트 대상은 풀이와 대안 풀이를 포함해 최대 {MAX_SOLUTIONS}개여야 합니다."]

    issues: list[str] = []
    specs: list[AlgorithmSolutionSpec] = []
    seen_sections: set[str] = set()
    allowed_sections = {"풀이", "다른 풀이 방법"}

    for index, item in enumerate(raw_solutions, 1):
        prefix = f"테스트 명세 {index}"
        if not isinstance(item, dict):
            issues.append(f"{prefix}: 객체 형식이어야 합니다.")
            continue
        section = item.get("section")
        if section not in allowed_sections:
            issues.append(f"{prefix}: section은 '풀이' 또는 '다른 풀이 방법'이어야 합니다.")
            continue
        if section in seen_sections:
            issues.append(f"{prefix}: 같은 섹션을 두 번 지정했습니다.")
            continue
        seen_sections.add(section)

        block_index = item.get("block_index")
        if not isinstance(block_index, int) or isinstance(block_index, bool) or block_index < 0:
            issues.append(f"{prefix}: block_index는 0 이상의 정수여야 합니다.")
            continue
        entrypoint = item.get("entrypoint")
        if not isinstance(entrypoint, str) or not _ENTRYPOINT_RE.fullmatch(entrypoint):
            issues.append(f"{prefix}: entrypoint는 function_name 또는 Solution.method_name 형식이어야 합니다.")
            continue

        section_content = sections.get(section, "")
        python_blocks = [
            block for block in iter_fenced_code_blocks(section_content)
            if block.complete and block.language in {"python", "py", "python3"}
        ]
        if block_index >= len(python_blocks):
            issues.append(
                f"{prefix}: {section} 섹션의 Python 코드 블록 {block_index}번을 찾을 수 없습니다."
            )
            continue
        source = python_blocks[block_index].body
        if len(source) > MAX_SOLUTION_CHARS:
            issues.append(f"{prefix}: 실행할 코드가 너무 깁니다. 핵심 풀이 코드만 남길 것.")

        cases = item.get("cases")
        if not isinstance(cases, list) or not MIN_CASES_PER_SOLUTION <= len(cases) <= MAX_CASES_PER_SOLUTION:
            issues.append(
                f"{prefix}: cases는 {MIN_CASES_PER_SOLUTION}~{MAX_CASES_PER_SOLUTION}개의 테스트를 포함해야 합니다."
            )
            continue
        if not any(isinstance(case, dict) and case.get("source_example") is True for case in cases):
            issues.append(f"{prefix}: 공식 문제 지문의 예시 테스트를 source_example=true로 최소 1개 포함할 것.")

        valid_cases: list[dict[str, Any]] = []
        for case_index, case in enumerate(cases, 1):
            case_prefix = f"{prefix}의 테스트 {case_index}"
            if not isinstance(case, dict):
                issues.append(f"{case_prefix}: 객체 형식이어야 합니다.")
                continue
            args = case.get("args")
            kwargs = case.get("kwargs", {})
            if not isinstance(args, list) or not isinstance(kwargs, dict):
                issues.append(f"{case_prefix}: args는 배열, kwargs는 객체여야 합니다.")
                continue
            if "expected" not in case:
                issues.append(f"{case_prefix}: expected 값이 없습니다.")
                continue
            comparison = case.get("comparison", "exact")
            if comparison not in {"exact", "unordered_list"}:
                issues.append(f"{case_prefix}: comparison은 exact 또는 unordered_list만 지원합니다.")
                continue
            if comparison == "unordered_list" and (
                not isinstance(case["expected"], list)
            ):
                issues.append(f"{case_prefix}: unordered_list 비교의 expected는 배열이어야 합니다.")
                continue
            values = [args, kwargs, case["expected"]]
            if "expected_args" in case:
                if not isinstance(case["expected_args"], list):
                    issues.append(f"{case_prefix}: expected_args는 배열이어야 합니다.")
                    continue
                values.append(case["expected_args"])
            if not all(_is_json_value(value) for value in values):
                issues.append(f"{case_prefix}: args/kwargs/expected는 유효한 JSON 값이어야 합니다.")
                continue
            valid_cases.append({
                "args": args,
                "kwargs": kwargs,
                "expected": case["expected"],
                "comparison": comparison,
                "expected_args": case.get("expected_args"),
            })
        if len(valid_cases) == len(cases):
            specs.append(AlgorithmSolutionSpec(section, block_index, entrypoint, tuple(valid_cases)))

    # A Python alternative is only required to be tested when one is actually present.
    for required_section in ("풀이", "다른 풀이 방법"):
        python_blocks = [
            block for block in iter_fenced_code_blocks(sections.get(required_section, ""))
            if block.complete and block.language in {"python", "py", "python3"}
        ]
        if python_blocks and required_section not in seen_sections:
            issues.append(f"{required_section} 섹션에 실행 가능한 Python 코드가 있지만 테스트 명세가 없습니다.")
    if "풀이" not in seen_sections:
        issues.append("주요 풀이 섹션에 대한 실행 테스트 명세가 필요합니다.")

    return specs, issues


def _validate_solution_source(source: str) -> list[str]:
    issues: list[str] = []
    try:
        tree = ast.parse(source)
        compile(tree, "<algorithm-solution>", "exec")
    except SyntaxError as exc:
        return [f"실행 테스트 코드의 문법/컴파일 오류({exc.lineno or 1}행): {exc.msg}."]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in _ALLOWED_IMPORTS:
                    issues.append(f"실행 코드에서 허용하지 않는 import를 사용합니다: {root}.")
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                issues.append("실행 코드의 상대 import는 허용하지 않습니다.")
            elif node.module.split(".", 1)[0] not in _ALLOWED_IMPORTS:
                issues.append(f"실행 코드에서 허용하지 않는 import를 사용합니다: {node.module}.")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BLOCKED_CALLS:
                issues.append(f"실행 코드에서 제한된 함수 호출을 사용합니다: {node.func.id}.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            issues.append("실행 코드에서 내부/dunder 속성 접근은 허용하지 않습니다.")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            issues.append("실행 코드에서 dunder 이름 접근은 허용하지 않습니다.")
    return list(dict.fromkeys(issues))


_RUNNER_SCRIPT = r'''
import builtins
import contextlib
import io
import json
import sys


_ALLOWED_IMPORTS = {
    "array", "bisect", "collections", "copy", "decimal", "enum",
    "fractions", "functools", "heapq", "itertools", "math", "operator",
    "random", "re", "statistics", "string", "typing", "__future__",
}
_ORIGINAL_IMPORT = builtins.__import__


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level:
        raise ImportError("relative imports are disabled")
    root = (name or "").split(".", 1)[0]
    if root not in _ALLOWED_IMPORTS:
        raise ImportError("module is not in the algorithm runner allowlist")
    return _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)


_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "classmethod", "complex", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hash",
    "hex", "int", "isinstance", "issubclass", "iter", "len", "list",
    "map", "max", "min", "next", "object", "oct", "ord", "pow",
    "property", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "staticmethod", "str", "sum", "super", "tuple", "type",
    "zip", "Exception", "ArithmeticError", "AssertionError", "IndexError",
    "KeyError", "LookupError", "MemoryError", "NameError", "NotImplementedError",
    "OverflowError", "RecursionError", "RuntimeError", "StopIteration",
    "TypeError", "ValueError", "ZeroDivisionError",
)
_SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}
_SAFE_BUILTINS.update({
    "__build_class__": builtins.__build_class__,
    "__import__": _restricted_import,
    "print": lambda *args, **kwargs: None,
})


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


def _build_tree(values):
    if not values or values[0] is None:
        return None
    root = TreeNode(values[0])
    queue = [root]
    index = 1
    qindex = 0
    while queue and index < len(values):
        node = queue[qindex]
        qindex += 1
        if index < len(values) and values[index] is not None:
            node.left = TreeNode(values[index])
            queue.append(node.left)
        index += 1
        if index < len(values) and values[index] is not None:
            node.right = TreeNode(values[index])
            queue.append(node.right)
        index += 1
    return root


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        kind = value.get("__type__")
        if kind == "TreeNode":
            return _build_tree(value.get("level_order", []))
        if kind == "ListNode":
            items = value.get("values", [])
            dummy = ListNode()
            current = dummy
            for item in items:
                current.next = ListNode(item)
                current = current.next
            return dummy.next
        return {key: _decode(item) for key, item in value.items()}
    return value


def _tree_values(root):
    if root is None:
        return []
    output = []
    queue = [root]
    index = 0
    seen = set()
    while index < len(queue):
        node = queue[index]
        index += 1
        if node is None:
            output.append(None)
            continue
        identity = id(node)
        if identity in seen:
            raise ValueError("cyclic TreeNode output")
        seen.add(identity)
        output.append(_normalize(node.val))
        queue.append(node.left)
        queue.append(node.right)
        if index > 5000:
            raise ValueError("TreeNode output is too large")
    while output and output[-1] is None:
        output.pop()
    return output


def _list_values(head):
    values = []
    seen = set()
    while head is not None:
        identity = id(head)
        if identity in seen:
            raise ValueError("cyclic ListNode output")
        seen.add(identity)
        values.append(_normalize(head.val))
        head = head.next
        if len(values) > 5000:
            raise ValueError("ListNode output is too large")
    return values


def _normalize(value):
    if isinstance(value, TreeNode):
        return _tree_values(value)
    if isinstance(value, ListNode):
        return _list_values(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, set):
        items = [_normalize(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    raise TypeError("solution returned an unsupported value type: " + type(value).__name__)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _equal(actual, expected, comparison):
    if comparison == "unordered_list":
        if not isinstance(actual, list) or not isinstance(expected, list):
            return False
        actual = sorted((_canonical(item) for item in actual))
        expected = sorted((_canonical(item) for item in expected))
        return actual == expected
    return _canonical(actual) == _canonical(expected)


def main():
    payload = json.loads(sys.stdin.read())
    source = payload["source"]
    entrypoint = payload["entrypoint"]
    cases = payload["cases"]

    namespace = {
        "__builtins__": _SAFE_BUILTINS,
        "__name__": "__algorithm_solution__",
        "TreeNode": TreeNode,
        "ListNode": ListNode,
    }
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(source, "<algorithm-solution>", "exec"), namespace, namespace)

    results = []
    for case_number, case in enumerate(cases, 1):
        args = _decode(case.get("args", []))
        kwargs = _decode(case.get("kwargs", {}))
        try:
            if entrypoint.startswith("Solution."):
                solution_class = namespace.get("Solution")
                if not isinstance(solution_class, type):
                    raise TypeError("Solution class was not defined")
                method_name = entrypoint.split(".", 1)[1]
                target = getattr(solution_class(), method_name, None)
            else:
                target = namespace.get(entrypoint)
            if not callable(target):
                raise TypeError("entrypoint is not callable")
            with contextlib.redirect_stdout(io.StringIO()):
                actual_raw = target(*args, **kwargs)
            actual = _normalize(actual_raw)
            passed = _equal(actual, case["expected"], case.get("comparison", "exact"))
            if "expected_args" in case:
                passed = passed and _equal(_normalize(args), _normalize(_decode(case["expected_args"])), "exact")
            results.append({
                "case": case_number,
                "passed": passed,
                "actual": actual,
                "expected": case["expected"],
            })
        except Exception as exc:
            results.append({
                "case": case_number,
                "passed": False,
                "error": type(exc).__name__ + ": " + str(exc)[:180],
            })
    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, allow_nan=False))


try:
    main()
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "error": type(exc).__name__ + ": " + str(exc)[:220],
    }, ensure_ascii=False))
    raise SystemExit(0)
'''


def _resource_limiter():
    """Best-effort POSIX limits; Windows relies on the timeout and restricted runner."""
    try:
        import resource

        if hasattr(resource, "RLIMIT_CPU"):
            resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        if hasattr(resource, "RLIMIT_AS"):
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        if hasattr(resource, "RLIMIT_FSIZE"):
            resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        if hasattr(resource, "RLIMIT_NOFILE"):
            resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except Exception:
        pass


def _run_one_solution(source: str, spec: AlgorithmSolutionSpec) -> list[str]:
    source_issues = _validate_solution_source(source)
    if source_issues:
        return source_issues
    payload = {
        "source": source,
        "entrypoint": spec.entrypoint,
        "cases": list(spec.cases),
    }
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(serialized) > MAX_MANIFEST_CHARS * 2:
        return ["실행 테스트 입력이 너무 큽니다. 테스트 데이터를 축소할 것."]

    with tempfile.TemporaryDirectory(prefix="algorithm-test-") as temp_dir:
        env = {
            "PATH": os.defpath,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        kwargs: dict[str, Any] = {}
        if os.name != "nt":
            kwargs["preexec_fn"] = _resource_limiter
        command = [sys.executable, "-I", "-S", "-c", _RUNNER_SCRIPT]
        try:
            completed = subprocess.run(
                command,
                input=serialized,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=temp_dir,
                env=env,
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
                **kwargs,
            )
        except subprocess.TimeoutExpired:
            return [f"실행 제한 시간({RUN_TIMEOUT_SECONDS}초)을 초과했습니다. 무한 루프 또는 비효율적인 풀이를 확인할 것."]
        except OSError as exc:
            return [f"격리 실행 프로세스를 시작하지 못했습니다: {type(exc).__name__}."]

    if completed.returncode != 0:
        return [f"풀이 실행 프로세스가 비정상 종료되었습니다(exit={completed.returncode})."]
    try:
        response = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return ["풀이 실행 결과를 읽지 못했습니다. 실행 코드 또는 출력 형식을 확인할 것."]
    if not response.get("ok"):
        return [f"풀이 초기화 오류: {response.get('error', 'unknown error')}"]

    issues = []
    for result in response.get("results", []):
        if result.get("passed"):
            continue
        case_number = result.get("case", "?")
        if result.get("error"):
            issues.append(f"테스트 {case_number} 실행 중 {result['error']}.")
        else:
            expected = json.dumps(result.get("expected"), ensure_ascii=False)[:160]
            actual = json.dumps(result.get("actual"), ensure_ascii=False)[:160]
            issues.append(f"테스트 {case_number} 결과 불일치: 기대값 {expected}, 실제값 {actual}.")
    return issues


def validate_and_run_algorithm_tests(raw: str, sections: dict[str, str]) -> list[str]:
    """Validate hidden test metadata, then execute each declared solution against its cases."""
    specs, issues = parse_algorithm_test_manifest(raw, sections)
    if issues:
        return issues

    all_issues = []
    for spec in specs:
        blocks = [
            block for block in iter_fenced_code_blocks(sections.get(spec.section, ""))
            if block.complete and block.language in {"python", "py", "python3"}
        ]
        if spec.block_index >= len(blocks):
            all_issues.append(f"{spec.section}: 테스트 대상 Python 코드 블록을 찾을 수 없습니다.")
            continue
        code_issues = _run_one_solution(blocks[spec.block_index].body, spec)
        all_issues.extend(f"{spec.section} 실행 테스트: {issue}" for issue in code_issues)
    return all_issues
