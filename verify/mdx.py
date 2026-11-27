"""Small MDX text-safety helpers shared by rendering and publishing."""

import re
from urllib.parse import quote

_FENCE_START_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)([^`\n]*?)\1(?!`)")
_MDX_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9._:-]*)(?:\s+[^<>]*?)?\s*/?>|<>|</>")
_MARKDOWN_LINK_RE = re.compile(r"(?P<prefix>!?\[[^\]\n]*\]\()(?P<url><[^>\n]*>|[^)\s]+)(?P<suffix>\))")
_COMPARISON_RE = re.compile(r"(?<=\w)(\s*)<(?=\s|=|\d)")
_ADJACENT_COMPARISON_RE = re.compile(r"(?<=\w)<(?=[A-Za-z0-9])")

# Preserve ordinary HTML phrasing/layout tags that MDX can safely render.
# Script/style/iframe and arbitrary unknown lowercase tags are treated as
# literal text, not executable markup. Uppercase tags are project MDX components.
_SAFE_HTML_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "dd",
    "del", "details", "div", "dl", "dt", "em", "figcaption", "figure", "h1",
    "h2", "h3", "h4", "h5", "h6", "hr", "i", "kbd", "li", "mark", "ol",
    "p", "pre", "q", "s", "small", "span", "strong", "sub", "summary",
    "sup", "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}


def _encode_markdown_link_angles(value: str) -> str:
    """Percent-encode angle brackets in Markdown link destinations.

    Markdown link destinations are not ordinary prose: HTML entities inside a
    URL may change its meaning. Keep optional CommonMark angle delimiters while
    encoding angle brackets that are part of the URL itself.
    """
    def replace(match: re.Match) -> str:
        raw_url = match.group("url")
        if raw_url.startswith("<") and raw_url.endswith(">"):
            inner = raw_url[1:-1]
            safe_url = quote(inner, safe=":/?#[]@!$&'()*+,;=%")
            return match.group("prefix") + "<" + safe_url + ">" + match.group("suffix")
        safe_url = quote(raw_url, safe=":/?#[]@!$&'()*+,;=%")
        return match.group("prefix") + safe_url + match.group("suffix")

    return _MARKDOWN_LINK_RE.sub(replace, value)


def normalize_mdx_text(text: str) -> tuple[str, int]:
    """Normalize prose that could be parsed as JSX while preserving code.

    Comparison operators and unknown/lowercase HTML-like tags are escaped as
    text. Known safe HTML tags and uppercase project MDX components are kept.
    Code fences, inline code, and YAML frontmatter are preserved verbatim.
    Markdown link destinations are URL-encoded before tag detection.
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

        value = _INLINE_CODE_RE.sub(hold, line)
        value = _encode_markdown_link_angles(value)

        def keep_or_escape_tag(match: re.Match) -> str:
            nonlocal replacements
            whole = match.group(0)
            tag_match = re.match(r"</?([A-Za-z][A-Za-z0-9._:-]*)", whole)
            if whole in {"<>", "</>"}:
                return hold(match)
            tag_name = tag_match.group(1) if tag_match else ""
            if tag_name[:1].isupper() or tag_name.casefold() in _SAFE_HTML_TAGS:
                return hold(match)
            replacements += 1
            return whole.replace("<", "&lt;").replace(">", "&gt;")

        value = _MDX_TAG_RE.sub(keep_or_escape_tag, value)

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
