"""
알고리즘 / 코딩테스트 문제 풀이 — 구조화 노트
========================================================
소스: LeetCode (난이도·태그·지문 전부 공개 GraphQL로 제공)
섹션: 문제 / 접근 방법 / 풀이 / 다른 풀이 방법 / 추가 참고사항

LeetCode 문제는 영어라 Writer가 한국어로 번역/요약하도록 프롬프트에 명시했고,
지문을 그대로 복사하지 않습니다. 원문 링크는 항상 노트 하단에 자동으로 붙습니다.
"""

from sources.algorithm import leetcode_candidates, problem_context_text
from topics._common import TopicSpec, run_topic

KEY = "algorithm"
LABEL = "알고리즘 문제 풀이"
SECTION_NAMES = ["문제", "접근 방법", "풀이", "다른 풀이 방법", "추가 참고사항"]


def _gather_candidates() -> list:
    return leetcode_candidates(limit=6)


def _build_context(chosen: dict):
    title_slug = chosen.get("title_slug")
    if not title_slug:
        return {"context_text": "", "source_url": None}
    context = problem_context_text(title_slug)
    if not context:
        return {"context_text": "", "source_url": None}
    tags = ", ".join(chosen.get("tags", []))
    if tags:
        context += f"\n\n관련 태그(참고용, 다른 풀이 방법 섹션에 활용 가능): {tags}"
    return {"context_text": context, "source_url": chosen.get("link"),
            "sources": [{"platform": "LeetCode", "title": chosen["title"], "url": chosen.get("link"), "author": None}]}


SPEC = TopicSpec(
    key=KEY,
    label=LABEL,
    category_prefix="[코딩테스트]",
    tag="Algorithm",
    section_names=SECTION_NAMES,
    gather_candidates=_gather_candidates,
    scout_criteria=(
        "아래 후보는 LeetCode에서 가져온 문제들이다. 판단 기준: (1) 코딩테스트에 "
        "자주 나올 법한 범용적인 유형인가(자료구조, 완전탐색, DP, 그리디, 그래프 "
        "등) (2) 난이도가 너무 극단적이지 않은가 (3) 제목만 봤을 때 짐작 가능한 "
        "전형적인 유형 문제를 우선한다."
    ),
    writer_role="알고리즘 문제 풀이 노트 작성자",
    writer_goal="주어진 영어 문제 지문을 바탕으로 문제-접근-풀이 구조의 한국어 노트를 작성한다",
    writer_backstory=(
        "코딩테스트 풀이를 문제-접근-풀이 구조로 정리해 레퍼런스처럼 제공하는 "
        "작성자. 영어 문제 지문을 한국어로 정확하게 번역/요약하되 원문을 그대로 "
        "베끼지 않고 핵심만 정리하며, 코드는 실제로 동작할 법한 수준으로 구체적으로 "
        "작성한다. 시간복잡도를 항상 명시한다."
    ),
    reviewer_role="알고리즘 풀이 검수자",
    reviewer_goal="풀이가 정확하고 실제로 동작할 법한 코드인지, 번역이 정확한지 검토한다",
    reviewer_checklist=(
        "'문제' 섹션이 영어 원문을 정확히 반영하면서도 한국어로 자연스럽게 "
        "요약됐는가, 코드가 문법적으로 타당하고 문제의 입출력 조건에 맞을 것으로 "
        "보이는가, 시간복잡도가 명시되어 있는가, '다른 풀이 방법'이 실제로 다른 "
        "접근인가(같은 풀이를 변수명만 바꾼 것이 아닌가)"
    ),
    build_context=_build_context,
    code_required_sections=("풀이",),
    extra_writer_rules=(
        "- 풀이: 전체 코드를 코드블록으로 넣고, 시간복잡도와 공간복잡도를 명시할 것\n"
        "- 다른 풀이 방법: 접근이 실제로 다른 풀이만(예: 완전탐색 vs 해시맵), 복잡도 비교 포함"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
