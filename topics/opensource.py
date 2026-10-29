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
- 본문은 최소 4,500자, 권장 5,000~7,000자로 작성한다. 같은 내용을 반복해 분량을 채우지 않는다.
- 독자가 프로젝트의 정체, 실제 구성, 대표적인 동작 또는 자료 탐색 흐름, 장단점과 한계를 이해하도록 설명한다. README 요약을 길게 늘여 쓰지 않는다.
- 각 섹션은 서로 다른 질문에 답한다. 프로젝트의 성격에 따라 필요한 섹션의 비중을 조정하되, 관련성이 낮은 보안 위험·사회적 효과·성능 한계를 억지로 만들지 않는다.

[저장소 유형부터 판별할 것]
- 먼저 프로젝트가 실행 가능한 라이브러리/프레임워크인지, 학습용 코드인지, 링크 컬렉션인지, 개발 도구인지 분류하고 첫 섹션에 명시한다.
- 라이브러리/프레임워크라면 실제 구현 경로와 API를 분석한다. 링크 컬렉션이라면 큐레이션 구조, 카테고리, 선택한 링크의 범위와 한계를 분석한다. 학습용 자료라면 학습 경로와 예제의 완성도를 분석한다.
- 저장소에 코드가 없거나 대표 구현 코드를 읽지 못했다면 내부 알고리즘을 구현한 것처럼 설명하지 않는다. 링크 컬렉션에 있는 외부 링크의 내용도 실제 원문을 수집하지 않았다면 그 제목/설명 이상으로 단정하지 않는다.

[사실 검증]
- 저장소 파일 경로는 실제 Git 트리와 대조된다. 참고 자료에 없거나 확인되지 않은 파일·함수·설정값을 만들어내지 않는다.
- 공식 파일 원문에서 확인한 사실, 일반적인 도메인 지식, 작성자의 해석을 구분한다. 원문이 근거가 되지 않는 해석은 '이 구조는 ...에 유리할 수 있습니다'처럼 추론으로 표시한다.
- 라이선스는 실제 LICENSE 파일을 우선한다. 보안 관련 조언은 SECURITY.md 또는 실제 코드에서 근거를 확인한 경우에만 작성한다. API 안정성, 성능, 배포 지원, 최신성, 별 수 등의 주장은 공식 원문이나 조회된 메타데이터가 뒷받침할 때만 사용한다.
- 외부 링크를 글에 넣을 때는 수집된 공식 파일 URL을 그대로 사용한다. 기억으로 URL이나 파일 경로를 조립하지 않는다.
- 현재 제공된 발췌에서 확인할 수 없는 사실은 중요하지 않으면 생략하고, 중요하다면 확인 불가/추정으로 구분한다. 근거가 없다는 이유만으로 반대 사실을 단정하지 않는다.

[기술 분석]
1. 한눈에 보는 섹션은 문제, 목표 사용자, 프로젝트 유형을 짧게 설명한다. 역사나 커뮤니티 일반론으로 분량을 늘리지 않는다.
2. 핵심 개념은 프로젝트를 이해하는 데 필요한 2~4개만 선택해 실제 파일이나 예제와 연결한다.
3. 저장소 구조 섹션은 중요한 폴더를 나열하는 것보다 책임과 연결 관계를 설명한다. 가능한 경우 입력 → 처리 → 출력 또는 사용자가 자료를 탐색하는 흐름으로 쓴다.
4. 구체적 예제 섹션은 실제로 읽은 파일이나 문서 하나를 중심으로 근거를 따라간다. 핵심 코드, 입력/출력, 실패 경로 또는 설계 선택을 설명한다. 코드를 읽지 못했다면 문서의 예제나 링크 한 건을 분석 대상으로 삼고 그 한계를 밝힌다.
5. 대안 비교는 1~2개로 제한한다. 역할이 서로 다른 프로젝트를 '성능이 더 좋다'처럼 측정 근거 없이 순위 매기지 않는다. 비교표는 각 열의 기준이 실제로 비교 가능한 경우에만 쓴다.
6. 보안·라이선스 섹션은 프로젝트에 실제로 관련되는 위험과 사용 조건만 다룬다. 보안 문서가 없는 경우 일반적인 공급망 위험을 프로젝트 자체의 취약점으로 표현하지 않는다.
7. 마지막 섹션은 이 프로젝트가 유용한 사람, 적합하지 않은 경우, 실제 도입/학습 전에 확인할 점을 요약한다. 앞 섹션의 결론을 다시 반복하지 않는다.

[문체와 링크]
- 독자를 위한 자연스러운 설명형 한국어로 작성한다. 긴 정의 목록·과장 표현·막연한 찬사를 피한다.
- 파일명과 경로는 백틱으로 감싼다. 프로젝트에 관한 중요한 주장은 가능하면 문장 안의 링크로 실제 원문 파일과 연결한다.
- 출처는 실제로 읽은 공식 README, 코드, LICENSE, 설정 문서만 적는다. 마지막 출처 목록은 핵심 자료 3~6개 정도로 제한한다.
- 코드 발췌는 원문과 정확히 일치해야 한다. 생략한 부분이 있다면 생략 표시를 명시하고, 설명용 의사 코드라면 실제 코드처럼 제시하지 않는다.
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
    reviewer_goal="중대 사실 오류, 근거 없는 구현 주장, 출처 불일치와 독자 오해를 만드는 핵심 결함을 검수한다. 사소한 문체 취향은 통과를 막지 않는다",
    reviewer_checklist=(
        "저장소 유형에 맞는 분석인가, 중대한 사실 오류나 존재하지 않는 파일 경로가 있는가, 실제 파일 원문으로 동작/설계 주장을 뒷받침하는가, "
        "코드/링크/라이선스/보안 문서의 내용을 잘못 해석하지 않는가, 독자가 결과를 오해할 비교나 모순이 있는가, "
        "글의 상당 부분이 일반론이라 실제 프로젝트 분석이 거의 없는가, 서로 다른 섹션의 결론이 반복되는가, "
        "근거가 있는 출처 링크를 사용하는가. "
        "통과를 막는 것은 검증 가능한 중대 오류와 핵심 분석 결함뿐이다. 사소한 문체 취향, 부수적인 누락, 발췌에 없는 주변 사실에 대한 추측은 실패 사유가 아니다. "
        "실제 오류가 있을 경우 최대 5개 지적을 하되, 각 지적은 대상 섹션, 원문 근거, 구체적인 수정 방법을 포함하고 중복하지 않는다."
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
    min_section_chars=250,
    min_total_chars=2500,
    max_rounds=3,
    long_form_guidance=LONG_FORM_GUIDANCE,
    extra_writer_rules=(
        "- 먼저 프로젝트의 성격(학습 자료, 실행 도구, 라이브러리 등)을 확인하고 그 성격에 맞는 분석을 할 것\n"
        "- 반드시 참고 자료에 실제로 포함된 구현 파일/문서를 연결할 것. 파일 경로만 수집된 경우 코드 동작을 추론하지 말 것\n"
        "- 섹션마다 다른 질문에 답하고, 동일한 결론이나 도메인 정의를 반복하지 말 것\n"
        "- 프로젝트와 직접 관련이 없는 보안 위험이나 사회적 효과를 억지로 덧붙이지 말 것\n"
        "- 출처 링크는 확인한 공식 저장소 파일에만 연결하고, 조회 시점이 필요한 통계는 시점을 표시할 것"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
