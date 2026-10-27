"""
Writer 출력 형식 파서 — JSON 대신 "제목:/요약: + ## 섹션" 마크다운 형식을 씁니다.
========================================================================
이전 버전은 Writer에게 JSON을 시켰는데, 코드가 들어가면 문자열 안의 따옴표·줄바꿈 때문에
JSON이 깨지는 경우가 많아서 5라운드 내내 파싱에 실패했고, 그 결과가 제목이 "untitled"인 빈 글로
저장됐습니다. 코드블록이 핵심인 글에는 마크다운 형식이 훨씬 자연스럽고(이스케이프 불필요),
LLM이 안정적으로 따릅니다.

형식:
    제목: [트러블슈팅] 핵심 키워드
    요약: 한 문장

    ## 현상
    본문 ... (```코드블록``` 그대로)

    ## 원인
    ...
"""

import re

_TITLE_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:제목|title)(?:\*\*)?\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:요약|summary)(?:\*\*)?\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s{0,3}#{2,3}\s*(.+?)\s*#*\s*$")
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*[:：]?\s*$")


def _norm(s: str) -> str:
    """'## 1. 해결 방법' / '해결방법:' / '**해결 방법**' 같은 변형을 같은 키로 맞춘다."""
    return re.sub(r"[\s\d.\-:：*#`()\[\]]+", "", s)


def _clean_inline(s: str) -> str:
    s = s.strip().strip("*").strip()
    if len(s) >= 2 and s[0] in "\"'“”" and s[-1] in "\"'“”":
        s = s[1:-1].strip()
    return s


def _unwrap_outer_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if len(lines) >= 3 and re.match(r"^```(?:markdown|md|text)?\s*$", lines[0].strip()) and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text


def parse_note_text(raw: str, section_names: list) -> dict | None:
    """반환: {"title","summary","sections":{이름: 본문}} — 아무것도 못 알아보면 None."""
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    text = _unwrap_outer_fence(text)
    if not text:
        return None

    names = {_norm(n): n for n in section_names}
    title = summary = ""
    sections: dict = {}
    current = None
    buf: list = []
    in_fence = False

    def flush():
        if current is not None:
            sections[current] = "\n".join(buf).strip()

    for line in text.splitlines():
        stripped = line.strip()
        if not in_fence:
            m = _TITLE_RE.match(line) if current is None else None
            if m and not title:
                title = _clean_inline(m.group(1))
                continue
            m = _SUMMARY_RE.match(line) if current is None else None
            if m and not summary:
                summary = _clean_inline(m.group(1))
                continue
            h = _HEADING_RE.match(line) or _BOLD_HEADING_RE.match(line)
            if h and _norm(h.group(1)) in names:
                flush()
                current, buf = names[_norm(h.group(1))], []
                continue
        if stripped.count("```") % 2 == 1:
            in_fence = not in_fence
        if current is not None:
            buf.append(line)
    flush()

    if not title and not any(sections.values()):
        return None
    return {"title": title, "summary": summary, "sections": sections}
