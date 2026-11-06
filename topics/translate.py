"""
Generate an English MDX for every Korean note that targets an English-enabled repository.

Fixed-outline topics use their configured heading map. Flexible-outline topics (paper reviews)
translate the headings actually written by the author, preserving their order and count.
"""

import re

from crewai import Task, Crew, Process

from crew_builder import build_translator_agent
from topics.note_format import parse_note_text
from output.note import _FENCE_RE

MAX_ATTEMPTS = 3
_HANGUL = re.compile(r"[가-힣]")
_COMMENT_STARTS = ("#", "//", "--", "/*", "*")
_SECTION_MARKER = re.compile(r"^\[SECTION\s+(\d+)\]\s*(?:[-:—]\s*)?(.+?)\s*$", re.IGNORECASE)
_INLINE_COMMENT = re.compile(r"\s+(?:#|//|--)\s.*$")


def _blocks(text: str) -> list:
    return [m.group(0) for m in _FENCE_RE.finditer(text or "")]


def _code_signature(block: str) -> list:
    """Compare executable lines while ignoring comments that may be translated."""
    inner = block.strip().strip("`")
    inner = re.sub(r"^[A-Za-z0-9_+#-]+(?=[ \t]|\r?\n)", "", inner, count=1)
    lines = []
    for line in inner.splitlines():
        value = _INLINE_COMMENT.sub("", line.strip())
        if value and not value.startswith(_COMMENT_STARTS):
            lines.append(value)
    return lines


def _outside_code(text: str) -> str:
    text = _FENCE_RE.sub(" ", text or "")
    return re.sub(r"`[^`]*`", " ", text)


def restore_code_blocks(en_text: str, ko_text: str) -> str:
    """Restore original fenced blocks if translation changed executable code."""
    ko_blocks = _blocks(ko_text)
    iterator = iter(ko_blocks)

    def replace(match):
        original = next(iterator, None)
        if original is None:
            return match.group(0)
        return match.group(0) if _code_signature(match.group(0)) == _code_signature(original) else original

    return _FENCE_RE.sub(replace, en_text)


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
    if _HANGUL.search(_outside_code(en["title"] + " " + en["summary"])):
        issues.append("Title/Summary에 한글이 남아 있음")
    for ko_name, en_name in zip(spec.section_names, spec.section_names_en):
        ko_text = ko["sections"].get(ko_name, "")
        en_text = en["sections"].get(en_name, "")
        if not en_text.strip():
            issues.append(f"'## {en_name}' 섹션이 비어 있음")
            continue
        if len(_blocks(en_text)) != len(_blocks(ko_text)):
            issues.append(f"'{en_name}' 섹션의 코드블록 개수가 원문({len(_blocks(ko_text))}개)과 다름")
        if _HANGUL.search(_outside_code(en_text)):
            issues.append(f"'{en_name}' 섹션의 코드 밖 문장에 한글이 남아 있음")
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
        "- Preserve every fenced code block exactly, including flow diagrams, commands, and code. Never translate or alter their contents.\n"
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
        "- Keep every fenced code block exactly as is. Never change code, error messages, filenames, or library names.\n"
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
