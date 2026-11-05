"""Small MDX text-safety helpers shared by rendering and publishing."""

import re

_FENCE_START_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)([^`\n]*?)\1(?!`)")
_MDX_TAG_RE = re.compile(
    r"</?[A-Za-z][A-Za-z0-9._:-]*(?:\s+[^<>]*?)?\s*/?>|<>|</>"
)
_COMPARISON_RE = re.compile(r"(?<=\w)(\s*)<(?=\s|=|\d)")
_ADJACENT_COMPARISON_RE = re.compile(r"(?<=\w)<(?=[A-Za-z0-9])")


def normalize_mdx_text(text: str) -> tuple[str, int]:
    """Escape prose comparison operators without touching code or JSX.

    MDX treats a raw '<' as the start of JSX. That makes ordinary prose such
    as 'n <= 50' fail during compilation. Code fences, inline code, JSX/HTML
    tags, and YAML frontmatter are preserved verbatim.
    """
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    replacements = 0
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    in_fence = False
    fence_char = ""
    fence_size = 0

    for index, line in enumerate(lines):
        if in_frontmatter:
            output.append(line)
            if index > 0 and line.strip() == "---":
                in_frontmatter = False
            continue

        fence_match = _FENCE_START_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_size = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_size:
                in_fence = False
                fence_char = ""
                fence_size = 0
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue

        protected: list[str] = []

        def hold(match: re.Match) -> str:
            protected.append(match.group(0))
            return f"\x00MDXSAFE{len(protected) - 1}\x00"

        # Protect inline code and explicit JSX/HTML tags before editing prose.
        value = _INLINE_CODE_RE.sub(hold, line)
        value = _MDX_TAG_RE.sub(hold, value)

        def escape_comparison(match: re.Match) -> str:
            nonlocal replacements
            replacements += 1
            return match.group(1) + "&lt;"

        value = _COMPARISON_RE.sub(escape_comparison, value)

        def escape_adjacent_comparison(match: re.Match) -> str:
            nonlocal replacements
            replacements += 1
            return "&lt;"

        value = _ADJACENT_COMPARISON_RE.sub(escape_adjacent_comparison, value)

        for token_index, original in enumerate(protected):
            value = value.replace(f"\x00MDXSAFE{token_index}\x00", original)
        output.append(value)

    return "".join(output), replacements
