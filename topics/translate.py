"""
영문판 생성 — 검증을 통과한 한국어 노트를 영어로 번역해서 en/ 폴더용 mdx로 만듭니다.
========================================================================
- 번역은 LLM이 하지만 **코드는 LLM을 믿지 않습니다**: 번역본의 코드블록이 원문과(주석을 뺀
  실제 코드 줄 기준으로) 다르면 원문 코드블록으로 바꿔치기합니다. 번역 중에 코드가
  바뀌는 일이 없게 하기 위함입니다.
- 코드블록 개수가 섹션별로 다르거나, 코드 밖에 한글이 남아 있거나, 섹션이 빠지면 지적 사항을
  붙여서 재시도(최대 3회)하고, 끝내 안 되면 영문판만 건너뜁니다(한국어 글은 영향 없음).
- GPU 시간이 들기 때문에 targets에 en_posts_dir가 하나도 없으면 아예 호출되지 않습니다.
"""

import re

from crewai import Task, Crew, Process

from crew_builder import build_translator_agent
from topics.note_format import parse_note_text
from output.note import _FENCE_RE

MAX_ATTEMPTS = 3
_HANGUL = re.compile(r"[가-힣]")
_COMMENT_STARTS = ("#", "//", "--", "/*", "*")


def _blocks(text: str) -> list:
    return [m.group(0) for m in _FENCE_RE.finditer(text or "")]


_INLINE_COMMENT = re.compile(r"\s+(?:#|//|--)\s.*$")


def _code_signature(block: str) -> list:
    """주석을 뺀 '실제 코드 줄'의 목록. 줄 전체가 주석인 줄과 줄 끝의 `  # 주석`은 무시한다
    (주석은 번역해도 되지만 코드는 바뀌면 안 되므로, 비교에서만 제외)."""
    inner = block.strip().strip("`")
    inner = re.sub(r"^[A-Za-z0-9_+#-]+(?=[ \t]|\r?\n)", "", inner, count=1)
    lines = []
    for ln in inner.splitlines():
        s = _INLINE_COMMENT.sub("", ln.strip())
        if s and not s.startswith(_COMMENT_STARTS):
            lines.append(s)
    return lines


def _outside_code(text: str) -> str:
    text = _FENCE_RE.sub(" ", text or "")
    return re.sub(r"`[^`]*`", " ", text)


def restore_code_blocks(en_text: str, ko_text: str) -> str:
    """영문 섹션의 코드블록을, 실제 코드(주석 제외)가 다르면 한국어 원문 블록으로 되돌린다."""
    ko_blocks = _blocks(ko_text)
    it = iter(ko_blocks)

    def repl(m):
        ko_block = next(it, None)
        if ko_block is None:
            return m.group(0)
        return m.group(0) if _code_signature(m.group(0)) == _code_signature(ko_block) else ko_block

    return _FENCE_RE.sub(repl, en_text)


def check_translation(spec, ko: dict, en: dict | None) -> list:
    if not en:
        return ["형식 파싱 실패 — 'Title:' 'Summary:' 줄 다음에 '## 섹션명' 헤더 형식을 지킬 것"]
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
            issues.append(f"'{en_name}' 섹션의 코드 밖 문장에 한글이 남아 있음 — 영어로 번역할 것")
    return issues


def _ko_markdown(spec, ko: dict) -> str:
    parts = [f"제목: {ko['title']}", f"요약: {ko['summary']}", ""]
    for name in spec.section_names:
        parts.append(f"## {name}\n{ko['sections'].get(name, '')}\n")
    return "\n".join(parts)


def translate_note(spec, ko: dict) -> dict | None:
    """ko: {"title","summary","sections":{한국어 섹션명: 본문}} -> 같은 구조의 영문 dict(섹션명은 영어) 또는 None."""
    agent = build_translator_agent()
    header_map = "\n".join(f"- '## {k}' -> '## {v}'" for k, v in zip(spec.section_names, spec.section_names_en))
    base = (
        "Translate the following Korean developer note into natural English.\n\n"
        "Rules:\n"
        "- Keep every fenced code block (``` ... ```) exactly as is. You may translate Korean comments inside "
        "code, but never change the code itself, error messages, file names, or library names.\n"
        "- Do not add or remove any information. Keep the same number of code blocks in every section.\n"
        f"- The title must start with '{spec.category_prefix_en}' (replacing the Korean category prefix).\n"
        "- Section headers must be translated exactly like this:\n" + header_map + "\n"
        "- Write plain, concise English. No Korean characters outside code.\n\n"
        "Output format (nothing else, no preface):\n"
        f"Title: {spec.category_prefix_en} ...\nSummary: one sentence\n\n"
        + "\n\n".join(f"## {v}\n(...)" for v in spec.section_names_en)
        + "\n\n--- SOURCE ---\n" + _ko_markdown(spec, ko)
    )
    prompt = base
    for attempt in range(1, MAX_ATTEMPTS + 1):
        task = Task(description=prompt, expected_output="English note in the given markdown format", agent=agent)
        Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        en = parse_note_text(str(task.output.raw), list(spec.section_names_en))
        issues = check_translation(spec, ko, en)
        if not issues:
            for ko_name, en_name in zip(spec.section_names, spec.section_names_en):
                en["sections"][en_name] = restore_code_blocks(en["sections"][en_name], ko["sections"].get(ko_name, ""))
            return en
        print(f"[번역 {attempt}/{MAX_ATTEMPTS}] 지적: {issues}")
        prompt = base + "\n\n--- PREVIOUS ATTEMPT HAD THESE PROBLEMS, FIX THEM ---\n" + "\n".join(f"- {i}" for i in issues)
    return None
