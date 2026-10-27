"""
검증 - 재작성 반복 루프
========================================================
글 하나를 "초안 작성 -> 기계적 검사 -> LLM 검수 -> (문제 있으면) 재작성"
순서로 max_rounds까지 반복합니다. 기계적 검사(JSON 형식, 필드 누락, 외국어 혼입
등)를 먼저 돌려서 싸고 확실한 문제부터 걸러내고, 통과하면 LLM 검수로 넘어갑니다.
"""

import json
import re
from difflib import SequenceMatcher

from crewai import Task, Crew, Process

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

# 한국어/영어/코드에 쓰이는 문자(한글, 영문, 숫자, 기본 기호) 밖의 CJK 문자 —
# 중국어/일본어 전용 한자·가나가 섞였는지 체크하는 용도
_FOREIGN_CJK_RE = re.compile(
    r"[\u3040-\u30ff\uff66-\uff9f]"  # 히라가나/가타카나
)


def extract_json(raw: str) -> dict | None:
    """모델이 JSON 앞뒤에 설명을 붙이거나 코드펜스로 감싸는 경우가 많아, 가장 큰
    {...} 블록만 추출해서 파싱한다."""
    # 추론 모델(<think>...</think>)이 JSON 앞에 생각 과정을 붙이는 경우 제거
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        # 가장 흔한 실패 원인: 이스케이프 안 된 큰따옴표. 단순 보정 시도 후 재파싱.
        fixed = m.group(0)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None


def detect_foreign_language_mixing(text: str) -> list[str]:
    if _FOREIGN_CJK_RE.search(text or ""):
        return ["한국어 외 다른 언어 문자(일본어 등)가 섞여 있음 — 전부 한국어로 다시 쓸 것"]
    return []


def _normalize_issue(issue: str) -> str:
    """검수 지적의 표현 차이를 줄여 같은 문제인지 비교한다."""
    value = (issue or "").casefold()
    value = re.sub(r"\b(?:현재\s*)?\d+[\d,]*(?:자|개|회|라운드)?\b", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return " ".join(value.split())


def _similar_issue_sets(left: list[str], right: list[str]) -> bool:
    """연속 검수 라운드의 지적이 대부분 같으면 재작성을 멈춘다."""
    left_norm = {_normalize_issue(x) for x in left if _normalize_issue(x)}
    right_norm = {_normalize_issue(x) for x in right if _normalize_issue(x)}
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True

    # 같은 항목을 약간 다른 표현으로 돌려 말한 경우도 감지한다.
    matched = 0
    for a in left_norm:
        if any(SequenceMatcher(None, a, b).ratio() >= 0.84 for b in right_norm):
            matched += 1
    overlap = matched / max(len(left_norm), len(right_norm))
    return overlap >= 0.8


def refine_loop(
