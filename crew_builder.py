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


def build_writer_agent(*, role: str, goal: str, backstory: str) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=f"{backstory}\n\n{COMMON_GUARDRAILS}",
        llm=llm_writer,
        verbose=True,
        max_iter=3,
        respect_context_window=True,
    )


def build_reviewer_agent(*, role: str, goal: str, checklist: str) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=(
            f"발행 직전 마지막 검수자. 확인 항목: {checklist}\n\n"
            "문제가 있으면 통과시키지 않고 구체적으로 뭘 고쳐야 하는지 말한다."
        ),
        llm=llm_verifier,
        verbose=True,
        max_iter=2,
        respect_context_window=True,
    )


def build_translator_agent() -> Agent:
    """한국어 기술 노트를 영어로 옮기는 에이전트. (다른 에이전트와 달리 한국어 전용 가드레일을 붙이지 않음)"""
    return Agent(
        role="기술 문서 번역가",
        goal="한국어 기술 노트를 자연스럽고 정확한 영어 기술 문서로 번역한다",
        backstory=(
            "Korean-to-English technical translator for developer documentation. Writes plain, concise "
            "English like official docs or a Stack Overflow answer. Never adds facts that are not in the "
            "source, never removes any. Keeps code, error messages, file names and library names exactly as "
            "they are, and translates only the prose (and code comments)."
        ),
        llm=llm_translator,
        verbose=True,
        max_iter=2,
        respect_context_window=True,
    )
