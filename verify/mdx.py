"""Small MDX text-safety helpers shared by rendering and publishing."""

import re

_FENCE_START_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)([^`\n]*?)\1(?!`)")
_MDX_TAG_RE = re.compile(
    r"</?([A-Za-z][A-Za-z0-9._:-]*)(?:\s+[^<>]*?)?\s*/?>|<>|</>"
)
_ALLOWED_TAGS = {
    "callout", "badge", "statgrid", "stat", "steps", "step", "compare",
    "comparepanel", "terminal", "filetree", "figure", "timeline",
    "timelineitem", "checklist", "kbd",
    "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code",
    "dd", "del", "details", "div", "dl", "dt", "em", "figcaption",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
    "li", "mark", "ol", "p", "picture", "pre", "q", "s", "small",
    "source", "span", "strong", "sub", "summary", "sup", "table",
    "tbody", "td", "tfoot", "th", "thead", "time", "tr", "u", "ul", "var",
}
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

        # Protect inline code first, then retain only supported MDX and safe HTML tags.
        value = _INLINE_CODE_RE.sub(hold, line)

        def handle_tag(match: re.Match) -> str:
            nonlocal replacements
            tag_name = match.group(1)
            raw = match.group(0)
            if tag_name and tag_name.casefold() in _ALLOWED_TAGS:
                return hold(match)
            replacements += 1
            return raw.replace("<", "&lt;").replace(">", "&gt;")

        value = _MDX_TAG_RE.sub(handle_tag, value)

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
