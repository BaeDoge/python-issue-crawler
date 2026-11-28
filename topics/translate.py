"""
Generate an English MDX for every Korean note that targets an English-enabled repository.

Fixed-outline topics use their configured heading map. Flexible-outline topics (paper reviews)
translate the headings actually written by the author, preserving their order and count.
"""

import re

from crewai import Task, Crew, Process

from crew_builder import build_translator_agent
from topics.note_format import parse_note_text
from verify.code_blocks import iter_fenced_code_blocks, mask_fenced_code_blocks, replace_fenced_code_blocks

MAX_ATTEMPTS = 3
_HANGUL = re.compile(r"[가-힣]")
_COMMENT_STARTS = ("#", "//", "--", "/*", "*")
_SECTION_MARKER = re.compile(r"^\[SECTION\s+(\d+)\]\s*(?:[-:—]\s*)?(.+?)\s*$", re.IGNORECASE)
_INLINE_COMMENT = re.compile(r"\s+(?:#|//|--)\s.*$")

_VERSION_ANCHOR_RE = re.compile(
    r"\b(?:python|pandas|numpy|django|flask|fastapi|pytorch|torch|node(?:\.js)?|"
    r"postgresql|mysql|cuda|ubuntu|windows|typescript|react|next\.js)\s+v?\d+(?:\.\d+){0,3}\b",
    re.IGNORECASE,
)
_EXCEPTION_ANCHOR_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception|Warning)\b")
_CLI_FLAG_ANCHOR_RE = re.compile(r"(?<!\w)--[A-Za-z][A-Za-z0-9-]*")


def extract_technical_anchors(text: str) -> set[str]:
    """Return inline-code commands/identifiers, version claims, errors, and CLI flags."""
    value = text or ""
    fence_char = chr(96)
    inline_pattern = re.escape(fence_char) + r"([^" + fence_char + r"\n]{1,140})" + re.escape(fence_char)
    anchors = {
        match.group(1).strip()
        for match in re.finditer(inline_pattern, value)
        if match.group(1).strip()
    }
    anchors.update(match.group(0) for match in _VERSION_ANCHOR_RE.finditer(value))
    anchors.update(match.group(0) for match in _EXCEPTION_ANCHOR_RE.finditer(value))
    anchors.update(match.group(0) for match in _CLI_FLAG_ANCHOR_RE.finditer(value))
    return anchors


def missing_technical_anchors(korean_text: str, english_text: str) -> list[str]:
    """Find technical literals that disappeared during translation."""
    english = (english_text or "").casefold()
    return sorted(
        anchor for anchor in extract_technical_anchors(korean_text)
        if anchor.casefold() not in english
    )


_GENERIC_TITLE_PLACEHOLDERS = {
    "core keyword", "core keywords", "key concept", "key concepts",
    "general overview", "overview", "introduction", "summary", "main topic",
}


def _title_specificity_issue(title: str, prefix: str) -> str | None:
    value = (title or "").strip()
    if value.startswith(prefix):
        value = value[len(prefix):].strip(" :：-–—")
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    if normalized in _GENERIC_TITLE_PLACEHOLDERS:
        return "영문 제목이 일반적인 임시 제목입니다. 실제 문제명이나 알고리즘 주제를 구체적으로 번역할 것"
    if len(normalized.split()) == 1 and normalized in {"keyword", "keywords", "topic", "problem"}:
        return "영문 제목이 실제 소재를 식별하지 못합니다. 문제명이나 구체적인 기술 주제를 제목에 포함할 것"
    return None



def _blocks(text: str) -> list[str]:
    return [block.raw for block in iter_fenced_code_blocks(text or "")]

def _code_signature(block: str) -> list[str]:
    """Compare executable lines while ignoring comments that may be translated."""
    parsed = list(iter_fenced_code_blocks(block or ""))
    if not parsed:
        return []
    lines = []
    for line in parsed[0].body.splitlines():
        value = _INLINE_COMMENT.sub("", line.strip())
        if value and not value.startswith(_COMMENT_STARTS):
            lines.append(value)
    return lines

def _outside_code(text: str) -> str:
    text = mask_fenced_code_blocks(text or "")
    return re.sub(r"`[^`]*`", " ", text)

def _block_language(block: str) -> str:
    parsed = list(iter_fenced_code_blocks(block or ""))
    return parsed[0].language if parsed else ""

def _flow_structure(block: str) -> tuple:
    """Keep flow diagram line/arrow structure while allowing labels to be translated."""
    parsed = list(iter_fenced_code_blocks(block or ""))
    if not parsed:
        return (0, ())
    lines = parsed[0].body.splitlines()
    connectors = re.compile(r"(?:→|->|-->|⇒|⇢)")
    return len(lines), tuple(tuple(connectors.findall(line)) for line in lines)

def restore_code_blocks(en_text: str, ko_text: str) -> str:
    """Preserve executable code; allow flow labels to be translated without changing diagram structure."""
    ko_blocks = iter(_blocks(ko_text))

    def replace(block):
        original = next(ko_blocks, None)
        if original is None:
            return block.raw
        if _block_language(block.raw) != _block_language(original):
            return original
        if _block_language(original) == "flow":
            return block.raw if _flow_structure(block.raw) == _flow_structure(original) else original
        return block.raw if _code_signature(block.raw) == _code_signature(original) else original

    return replace_fenced_code_blocks(en_text, replace)

def _ko_markdown(spec, ko: dict) -> str:
    parts = [f"제목: {ko['title']}", f"요약: {ko['summary']}", ""]
    for name, body in ko["sections"].items():
        parts.append(f"## {name}\n{body}\n")
    return "\n".join(parts)


def _fixed_translation_issues(spec, ko: dict, en: dict | None) -> list:
    if not en:
        return ["형식 파싱 실패 — Title/Summary와 지정된 영어 섹션 헤더 형식을 확인할 것"]
    issues = []
    if not en["title"].startswith(spec.category_prefix_en):
        issues.append(f"Title must start with '{spec.category_prefix_en}'")
    title_issue = _title_specificity_issue(en["title"], spec.category_prefix_en)
    if title_issue:
        issues.append(title_issue)
    if _HANGUL.search(_outside_code(en["title"] + " " + en["summary"])):
        issues.append("Title/Summary에 한글이 남아 있음")
    for ko_name, en_name in zip(spec.section_names, spec.section_names_en):
        ko_text = ko["sections"].get(ko_name, "")
        en_text = en["sections"].get(en_name, "")
        if not en_text.strip():
            issues.append(f"'## {en_name}' 섹션이 비어 있음")
            continue
        if any(not block.complete for block in iter_fenced_code_blocks(en_text)):
            issues.append(f"'{en_name}' 섹션에 닫히지 않은 코드 펜스가 있습니다.")
        if len(_blocks(en_text)) != len(_blocks(ko_text)):
            issues.append(f"'{en_name}' 섹션의 코드블록 개수가 원문({len(_blocks(ko_text))}개)과 다름")
        if _HANGUL.search(_outside_code(en_text)):
            issues.append(f"'{en_name}' 섹션의 코드 밖 문장에 한글이 남아 있음")
        if spec.key == "troubleshooting":
            missing_anchors = missing_technical_anchors(ko_text, en_text)
            if missing_anchors:
                preview = ", ".join(missing_anchors[:5])
                issues.append(f"'{en_name}' 섹션에서 기술 식별자/버전/명령이 누락되거나 변형됨: {preview}")
    return issues


def _flexible_translation_prompt(spec, ko: dict) -> str:
    sections = list(ko["sections"].items())
    output_sections = "\n\n".join(
        f"## [SECTION {index}] English heading translated naturally\n(Translate this section without adding or omitting information.)"
        for index, _ in enumerate(sections, 1)
    )
    source_sections = "\n\n".join(
        f"## [SECTION {index}] {heading}\n{body}"
        for index, (heading, body) in enumerate(sections, 1)
    )
    return (
        "Translate this Korean technical paper review into natural, readable English for software and AI developers.\n\n"
        "Rules:\n"
        "- Translate the actual section headings supplied below. Do not replace them with a generic fixed outline.\n"
        "- Preserve exactly the same number and order of sections. Do not merge, split, add, or omit sections.\n"
        "- Every output heading MUST begin with its matching marker, exactly '[SECTION N] ', followed by a concise English heading.\n"
        "- Keep executable code blocks (Python, shell, JSON, etc.) exactly as written. For fenced 'flow' diagrams only, translate visible labels into English while preserving every line and arrow connector in the same order.\n"
        "- Translate the actual subject/problem name in the title. Never use generic placeholders such as Core Keywords, Core Keyword, Overview, or Key Concepts.\n"
        "- Do not add facts, examples, metrics, or claims. Translate only the supplied content.\n"
        "- Use clear, natural English. No Korean characters outside code blocks.\n"
        f"- The title must start with '{spec.category_prefix_en}'.\n"
        "- Keep links, URLs, identifiers, filenames, model names, and technical terms accurate.\n\n"
        "Output only this format, with no preface:\n"
        f"Title: {spec.category_prefix_en} ...\nSummary: one sentence\n\n"
        f"{output_sections}\n\n--- SOURCE ---\n"
        f"Title: {ko['title']}\nSummary: {ko['summary']}\n\n{source_sections}"
    )


def _fixed_translation_prompt(spec, ko: dict) -> str:
    header_map = "\n".join(
        f"- '## {ko_name}' -> '## {en_name}'"
        for ko_name, en_name in zip(spec.section_names, spec.section_names_en)
    )
    output_sections = "\n\n".join(
        f"## {name}\n(Translate this section.)" for name in spec.section_names_en
    )
    return (
        "Translate the following Korean developer note into natural English.\n\n"
        "Rules:\n"
        "- Keep executable code blocks exactly as is. In fenced 'flow' diagrams, translate visible labels but preserve line count and arrow connectors. Never change commands, error messages, filenames, or identifiers.\n"
        "- Translate the actual subject/problem name in the title. Never use generic placeholders such as Core Keywords, Core Keyword, Overview, or Key Concepts.\n"
        "- Do not add or remove information. Keep the same number of code blocks in every section.\n"
        f"- The title must start with '{spec.category_prefix_en}'.\n"
        "- Section headers must use this exact mapping:\n" + header_map + "\n"
        "- Write concise English. No Korean characters outside code.\n\n"
        "Output format (nothing else):\n"
        f"Title: {spec.category_prefix_en} ...\nSummary: one sentence\n\n"
        f"{output_sections}\n\n--- SOURCE ---\n{_ko_markdown(spec, ko)}"
    )


def _translate_flexible_result(spec, ko: dict, raw: str) -> tuple[dict | None, list[str]]:
    parsed = parse_note_text(raw, [], allow_dynamic_sections=True)
    if not parsed:
        return None, ["영문 결과를 Markdown 섹션 형식으로 파싱하지 못함"]
    issues = []
    if not parsed["title"].startswith(spec.category_prefix_en):
        issues.append(f"Title must start with '{spec.category_prefix_en}'")
    title_issue = _title_specificity_issue(parsed["title"], spec.category_prefix_en)
    if title_issue:
        issues.append(title_issue)
    if not parsed["summary"].strip():
        issues.append("영문 Summary가 비어 있음")
    if _HANGUL.search(_outside_code(parsed["title"] + " " + parsed["summary"])):
        issues.append("Title/Summary에 한글이 남아 있음")

    ko_items = list(ko["sections"].items())
    en_items = list(parsed["sections"].items())
    if len(en_items) != len(ko_items):
        issues.append(f"섹션 수가 원문({len(ko_items)}개)과 다름: 번역 결과 {len(en_items)}개")

    translated_sections = {}
    section_map = {}
    for index, (ko_heading, ko_body) in enumerate(ko_items, 1):
        if index > len(en_items):
            continue
        marker_heading, en_body = en_items[index - 1]
        marker = _SECTION_MARKER.match(marker_heading)
        if not marker or int(marker.group(1)) != index:
            issues.append(f"{index}번째 영어 섹션에 [SECTION {index}] 마커가 없거나 순서가 바뀜")
            continue
        en_heading = marker.group(2).strip()
        if not en_heading:
            issues.append(f"{index}번째 영어 섹션 제목이 비어 있음")
            continue
        if _HANGUL.search(_outside_code(en_heading + " " + en_body)):
            issues.append(f"'{en_heading}' 섹션에 코드 밖 한글이 남아 있음")
        if any(not block.complete for block in iter_fenced_code_blocks(en_body)):
            issues.append(f"'{en_heading}' 섹션에 닫히지 않은 코드 펜스가 있습니다.")
        if len(_blocks(en_body)) != len(_blocks(ko_body)):
            issues.append(f"'{en_heading}' 섹션의 코드블록 개수가 원문과 다름")
        translated_sections[en_heading] = restore_code_blocks(en_body, ko_body)
        section_map[ko_heading] = en_heading

    if len(translated_sections) != len(ko_items):
        issues.append("영문 섹션 제목을 모두 추출하지 못함")
    if issues:
        return None, issues
    return {
        "title": parsed["title"],
        "summary": parsed["summary"],
        "sections": translated_sections,
        "section_map": section_map,
    }, []


def translate_note(spec, ko: dict) -> dict | None:
    """Return translated note data; flexible topics also return a Korean-to-English section_map."""
    agent = build_translator_agent()
    flexible = bool(spec.flexible_sections)
    base = _flexible_translation_prompt(spec, ko) if flexible else _fixed_translation_prompt(spec, ko)
    prompt = base

    for attempt in range(1, MAX_ATTEMPTS + 1):
        task = Task(
            description=prompt,
            expected_output="English note in the requested Markdown format",
            agent=agent,
        )
        Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        raw = str(task.output.raw)

        if flexible:
            translated, issues = _translate_flexible_result(spec, ko, raw)
            if translated:
                return translated
        else:
            en = parse_note_text(raw, list(spec.section_names_en))
            issues = _fixed_translation_issues(spec, ko, en)
            if not issues:
                for ko_name, en_name in zip(spec.section_names, spec.section_names_en):
                    en["sections"][en_name] = restore_code_blocks(
                        en["sections"][en_name], ko["sections"].get(ko_name, "")
                    )
                return en

        print(f"[번역 {attempt}/{MAX_ATTEMPTS}] 지적: {issues}")
        prompt = (
            base + "\n\n--- PREVIOUS TRANSLATION FAILED VALIDATION ---\n"
            + "\n".join(f"- {issue}" for issue in issues)
            + "\nCorrect every issue while preserving the original meaning and section order."
        )

    return None
