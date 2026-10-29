"""
CrewAI 에이전트 공통 빌더
========================================================
주제(트러블슈팅/알고리즘)마다 완전히 새로운 Agent 인스턴스를 만듭니다. 같은
에이전트를 재사용하면 backstory가 다른 주제에 새어 들어가는 문제가 있었어서,
빌더 함수만 공유하고 실제 Agent는 topics/*.py가 매번 새로 만들게 합니다.
"""

from crewai import Agent
from config import llm_scout, llm_writer, llm_verifier, llm_translator

COMMON_GUARDRAILS = (
    "⚠️ 항상 지킬 것: (1) 오직 한국어로만 쓴다 — 다른 언어 문자가 섞이면 안 된다. "
    "(2) 실제로 존재하는지 확신할 수 없는 내용을 지어내지 않는다 — 확실하지 않으면 "
    "주어진 자료 범위 안에서만 구체적으로 쓴다. (3) 요청받은 필드만 정확히 채운다. "
    "(4) 블로그 narrative체(길게 풀어쓰는 문체)가 아니라, 정보 전달 목적의 담백한 "
    "'습니다'체로 짧고 명확하게 쓴다. 반말이나 과장된 비유, 감탄사는 쓰지 않는다."
)


def build_scout_agent(*, judging_criteria: str) -> Agent:
    return Agent(
        role="콘텐츠 스카우트",
        goal="주어진 후보 목록 중 이번 작업 기준에 가장 잘 맞는 것 하나를 고른다",
        backstory=f"후보를 골라주는 리서처. 판단 기준: {judging_criteria}",
        llm=llm_scout,
        verbose=True,
        max_iter=2,
        respect_context_window=True,
    )


def build_writer_agent(*, role: str, goal: str, backstory: str, long_form: bool = False) -> Agent:
    style_guardrails = (
        "장문 기술 블로그 작성 모드: 자연스럽게 이어지는 설명형 문체를 사용하고, 독자가 배경·핵심 원리·실제 사례·한계까지 "
        "이해하도록 충분히 설명한다. 짧게 쓰라는 기본 규칙보다 주제별 분량과 분석 지침을 우선한다. "
        "그렇더라도 같은 결론을 반복하거나 근거 없는 추측으로 분량을 늘리지 않는다. "
        "프로젝트에서 확인한 사실, 일반적 배경지식, 분석자의 해석을 구분하고, 확인할 수 없는 파일·기능·수치를 만들지 않는다. "
        "출처는 실제로 읽은 공식 자료에만 연결한다."
        if long_form else COMMON_GUARDRAILS
    )
    return Agent(
        role=role,
        goal=goal,
        backstory=f"{backstory}\n\n{style_guardrails}",
        llm=llm_writer,
        verbose=True,
        max_iter=3,
        respect_context_window=True,
    )


def build_reviewer_agent(
    *, role: str, goal: str, checklist: str, long_form: bool = False,
) -> Agent:
    reviewer_rules = (
        "중대 사실 오류, 원문과 충돌하는 주장, 존재하지 않는 파일 경로, "
        "보안/라이선스 오정보, 독자를 오도하는 핵심 결함만 통과를 막는다. "
        "사소한 문체 취향, 부수적인 누락, 더 자세히 설명할 수 있다는 이유만으로 실패시키지 않는다. "
        "검증할 수 없는 주변 사실은 거짓이라고 단정하지 말고, 핵심 주장인지 먼저 판단한다. "
        "실제 오류가 없으면 반드시 passed=true와 빈 issues 목록을 반환한다."
        if long_form else
        "문제가 있으면 통과시키지 않고 구체적으로 뭘 고쳐야 하는지 말한다."
    )
    return Agent(
        role=role,
        goal=goal,
        backstory=f"발행 직전 마지막 검수자. 확인 항목: {checklist}\n\n{reviewer_rules}",
        llm=llm_verifier,
        verbose=True,
        max_iter=2,
        respect_context_window=True,
    )



def build_translator_agent() -> Agent:
    """한국어 기술 노트를 영어로 번역한다. 한국어 전용 작성 규칙은 적용하지 않는다."""
    return Agent(
        role="Technical documentation translator",
        goal="Translate Korean developer notes into accurate, natural English without changing technical meaning",
        backstory=(
            "Korean-to-English technical translator for developer documentation. Write concise, plain English. "
            "Do not add or remove facts. Preserve code, error messages, file names, identifiers, and library names; "
            "translate prose and comments only."
        ),
        llm=llm_translator,
        verbose=True,
        max_iter=2,
        respect_context_window=True,
    )
