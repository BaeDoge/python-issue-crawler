"""Small MDX text-safety helpers shared by rendering and publishing."""
import re

_FENCE_START_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)([^`\n]*?)\1(?!`)")
_MDX_TAG_RE = re.compile(r"</?(?:Callout|Badge|StatGrid|Stat|Steps|Step|Compare|ComparePanel|Terminal|FileTree|Figure|Timeline|TimelineItem|Checklist|Kbd)(?:\s+[^<>]*?)?\s*/?>")
_HTML_TAG_RE = re.compile(r"</?\s*[A-Za-z][A-Za-z0-9._:-]*(?:\s+[^<>]*?)?\s*/?>|<>|</>")
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.IGNORECASE)
_HREF_RE = re.compile(r'href\s*=\s*\"([^\"]*)\"', re.IGNORECASE)
_IMG_RE = re.compile(r"<img\b([^>]*)/?>", re.IGNORECASE)
_SRC_RE = re.compile(r'src\s*=\s*\"([^\"]*)\"', re.IGNORECASE)
_ALT_RE = re.compile(r'alt\s*=\s*\"([^\"]*)\"', re.IGNORECASE)
_COMPARISON_RE = re.compile(r"(?<=\w)(\s*)<(?=\s|=|\d)")
_ADJACENT_COMPARISON_RE = re.compile(r"(?<=\w)<(?=[A-Za-z0-9])")

def _safe_markdown_link(url: str, label: str) -> str:
    """Convert only web links to Markdown; never preserve executable URL schemes."""
    url = url.strip()
    label = re.sub(_HTML_TAG_RE, "", label).strip()
    if not label:
        label = url
    if url.lower().startswith(("https://", "http://", "mailto:")):
        return f"[{label}]({url})"
    return label

def _sanitize_raw_html(value: str) -> str:
    """Remove raw HTML from prose while keeping supported MDX components and links."""
    protected: list[str] = []
    def hold(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00MDXSAFE{len(protected) - 1}\x00"
    value = _INLINE_CODE_RE.sub(hold, value)
    value = _MDX_TAG_RE.sub(hold, value)
    def convert_anchor(match: re.Match) -> str:
        attributes, label = match.group(1), match.group(2)
        href = _HREF_RE.search(attributes)
        return _safe_markdown_link(href.group(1), label) if href else re.sub(_HTML_TAG_RE, "", label)
    value = _ANCHOR_RE.sub(convert_anchor, value)
    def convert_image(match: re.Match) -> str:
        attributes = match.group(1)
        src = _SRC_RE.search(attributes)
        alt = _ALT_RE.search(attributes)
        if not src:
            return alt.group(1) if alt else ""
        source = src.group(1).strip()
        if source.startswith(("https://", "http://", "/")):
            description = alt.group(1).strip() if alt else "image"
            return f"![{description}]({source})"
        return alt.group(1) if alt else ""
    value = _IMG_RE.sub(convert_image, value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</?(?:p|div|section|article|ul|ol|li|h[1-6]|blockquote|pre|table|thead|tbody|tr)\b[^>]*>", "\n", value, flags=re.IGNORECASE)
    value = _HTML_TAG_RE.sub("", value)
    for token_index, original in enumerate(protected):
        value = value.replace(f"\x00MDXSAFE{token_index}\x00", original)
    return value

def normalize_mdx_text(text: str) -> tuple[str, int]:
    """Escape prose comparison operators and remove raw HTML without touching code/frontmatter."""
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
        value = _sanitize_raw_html(line)
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
        output.append(value)
    return "".join(output), replacements