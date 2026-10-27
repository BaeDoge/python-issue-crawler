"""근거 중심의 장문 오픈소스 분석 주제.

후보 선정은 topics._common.run_topic의 Scout 에이전트가 자동 수행합니다.
"""
from __future__ import annotations

from sources.github_trending import discover_github_candidates, fetch_repository_context
from topics._common import TopicSpec, run_topic

KEY = "opensource"
LABEL = "GitHub 오픈소스 심층 분석"
SECTION_NAMES = [
    "한눈에 보는 프로젝트와 해결하려는 문제",
    "이해에 필요한 핵심 개념",
    "저장소 구조와 실제 동작 흐름",
    "구체적인 예제로 보는 설계 선택",
    "대안과 비교했을 때의 장단점",
    "보안·라이선스·도입 시 확인할 점",
    "한계와 추천 대상",
]

LONG_FORM_GUIDANCE = """
[글의 목표와 분량]
- 본문은 최소 4,500자, 권장 5,000~7,000자로 작성한다. 각 섹션은 대략 500~800자를 목표로 하되, 근거가 부족한 섹션을 억지로 늘리지 않는다.
- 독자가 프로젝트가 무엇을 하는지, 어떤 구조로 작동하는지, 어디에 유용하고 무엇을 주의해야 하는지 이해하는 글을 쓴다. 저장소 소개나 README 요약으로 끝내지 않는다.
- 일반적인 기술 배경은 이해에 필요한 만큼만 설명하고, 곧바로 해당 프로젝트의 문서·코드·예제와 연결한다.
- 저장소에서 확인한 사실, 도메인 일반 지식, 작성자의 해석을 구분한다. 프로젝트 고유 기능이라고 주장하려면 제공된 공식 파일 내용으로 근거를 댄다.
- 파일 트리에 경로가 존재한다는 사실만으로 그 파일의 내부 구현을 안다고 주장하지 않는다. 파일 내용이 참고 자료에 없으면 경로의 존재만 말하거나 해당 설명을 생략한다.
- 수치와 최신성 주장은 조회 시점과 출처를 밝혀야 한다. 근거가 부족하면 확인할 수 없다고 말하고, 추정으로 채우지 않는다.

[분석 깊이]
1. 첫 섹션은 해결하려는 문제와 사용자를 짧게 제시한 뒤, 이 프로젝트가 자료집·라이브러리·실행 도구 중 무엇인지 명확히 규정한다.
2. 개념 설명은 프로젝트를 이해하는 데 필요한 핵심 2~4개만 선택한다. 정의를 나열하지 말고 왜 이 프로젝트에서 중요한지 연결한다.
3. 실제 저장소 파일을 근거로 폴더 역할과 데이터 흐름을 설명한다. 구현 코드가 있는 경우 입력→주요 처리→출력/실패 경로 순으로 설명한다. 문서와 다이어그램 중심 프로젝트라면 그 사실을 명확히 하고 코드 구현이 있는 것처럼 쓰지 않는다.
4. 실제 사용 예시를 하나 골라 요구사항, 자료/코드 위치, 설계 선택, 트레이드오프를 구체적으로 추적한다. 숫자가 예시의 가정이라면 실제 운영 지표처럼 제시하지 않는다.
5. 비교 대상은 1~2개로 제한하고 대상별 역할과 장단점을 공정하게 비교한다. 우월성은 근거 없이 단정하지 않는다.
6. 라이선스는 GitHub API의 SPDX 표기만으로 결론 내리지 말고 실제 LICENSE 파일을 확인한다. 보안·개인정보·실행 권한·운영 위험 중 프로젝트와 관련 있는 항목만 다루며, 관련성이 낮다면 억지로 사회적 영향이나 위협을 만들어내지 않는다.
7. 끝에서는 누구에게 유용한지, 맞지 않을 수 있는 경우, 도입 전에 직접 확인할 사항을 구체적으로 정리한다.

[편집 기준]
- 같은 결론을 여러 섹션에서 반복하지 않는다. 각 섹션의 역할이 겹치면 한곳에만 둔다.
- 수사적인 도입, 스타 수를 품질 증거로 삼는 표현, 근거 없는 사회적 기여 주장을 피한다.
- 출처 링크는 실제로 읽은 공식 저장소와 파일에만 연결한다. 본문에서 최소 2~4개의 관련 파일/문서 링크를 연결하고, 끝에는 핵심 출처만 짧게 정리한다.
- 설치법과 기본 개념 설명이 전체 글의 대부분을 차지하지 않도록 한다. 중요한 분석은 저장소에서 확인한 구체적인 구조, 예제, 트레이드오프에 둔다.
"""

def _gather_candidates() -> list:
    payload = discover_github_candidates()
    candidates = []
    seen = set()
    # 최근 활동 후보가 목록을 독점하지 않도록 인기/최근 활동 결과를 번갈아 섞습니다.
    trending = payload.get("trending", [])
    popular = payload.get("popular", [])
    for index in range(max(len(trending), len(popular))):
        for group in (trending, popular):
            if index >= len(group):
                continue
            item = group[index]
            link = (item.get("link") or "").rstrip("/")
            if link and link.casefold() not in seen:
                seen.add(link.casefold())
                candidates.append(item)
            if len(candidates) >= 36:
                return candidates
    return candidates


def _build_context(chosen: dict) -> dict:
    return fetch_repository_context(chosen)


SPEC = TopicSpec(
    key=KEY,
    label=LABEL,
    category_prefix="[오픈소스 분석]",
    tag="OpenSource",
    section_names=SECTION_NAMES,
    gather_candidates=_gather_candidates,
    scout_criteria=(
        "후보 중에서 기술적 배경과 내부 동작을 분석할 공식 자료가 충분하고, 구체적인 예제로 기술적 판단을 설명할 수 있는 "
        "프로젝트를 선택한다. 단순히 별점이 높다는 이유만으로 선택하지 말고, 분야 다양성·실용성·자료 접근성을 고려한다. "
        "실제 구현이 주가 아닌 학습 자료집이라면 문서와 예제의 구조를 분석 대상으로 삼을 수 있다."
    ),
    writer_role="시니어 오픈소스 리서처이자 기술 블로그 저자",
    writer_goal=(
        "실제 저장소 자료를 근거로 프로젝트의 목적, 핵심 구조, 구체적인 예제, 설계 선택, 대안과 한계를 설명하는 "
        "읽기 좋은 장문 기술 분석 글을 작성한다"
    ),
    writer_backstory=(
        "문서와 소스 코드를 교차 확인하는 기술 저술가. 확인 가능한 사실과 일반적 배경 설명을 구분하고, "
        "불확실한 정보는 단정하지 않는다. 개발자와 기술 채용 담당자가 읽어도 분석 과정과 판단 근거를 따라갈 수 있게 쓴다."
    ),
    reviewer_role="기술 리서치 편집자 및 사실 검증자",
    reviewer_goal="근거, 정확성, 구체성, 중복 여부, 독자 가치와 출처의 일치 여부를 검수한다",
    reviewer_checklist=(
        "실제 프로젝트의 구조와 특징이 글의 중심인가, 제공된 파일 내용으로 주장을 뒷받침하는가, "
        "파일 존재 여부와 내부 구현을 혼동하지 않는가, 도메인 일반론이 과도하게 길거나 섹션 간 결론이 반복되지 않는가, "
        "구체적인 예제에서 입력·처리·결과 또는 설계 선택을 설명하는가, 비교가 공정하고 근거 없는 우월성 주장을 피하는가, "
        "라이선스 및 최신 수치가 실제 원문과 일치하는가, 관련성 낮은 보안·사회적 영향을 억지로 채우지 않는가, "
        "출처 링크가 실제 참고한 자료를 가리키는가"
    ),
    build_context=_build_context,
    category_prefix_en="[Open Source Analysis]",
    section_names_en=(
        "Project at a Glance and the Problem It Solves",
        "Key Concepts Needed to Understand It",
        "Repository Structure and Actual Flow",
        "A Concrete Example of Its Design Choices",
        "Trade-offs Compared with Alternatives",
        "Security, Licensing, and Adoption Checks",
        "Limitations and Who Should Use It",
    ),
    min_section_chars=350,
    min_total_chars=4500,
    max_rounds=4,
    long_form_guidance=LONG_FORM_GUIDANCE,
    extra_writer_rules=(
        "- 먼저 프로젝트의 성격(학습 자료, 실행 도구, 라이브러리 등)을 확인하고 그 성격에 맞는 분석을 할 것
"
        "- 반드시 참고 자료에 실제로 포함된 구현 파일/문서를 연결할 것. 파일 경로만 수집된 경우 코드 동작을 추론하지 말 것
"
        "- 섹션마다 다른 질문에 답하고, 동일한 결론이나 도메인 정의를 반복하지 말 것
"
        "- 프로젝트와 직접 관련이 없는 보안 위험이나 사회적 효과를 억지로 덧붙이지 말 것
"
        "- 출처 링크는 확인한 공식 저장소 파일에만 연결하고, 조회 시점이 필요한 통계는 시점을 표시할 것"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
