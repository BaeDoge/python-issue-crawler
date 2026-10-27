"""심층 장문 오픈소스 분석 주제. 후보는 Scout 에이전트가 자동 선택합니다."""
from __future__ import annotations

from sources.github_trending import discover_github_candidates, fetch_repository_context
from topics._common import TopicSpec, run_topic

KEY = "opensource"
LABEL = "GitHub 오픈소스 심층 분석"
SECTION_NAMES = [
    "프로젝트가 해결하려는 문제와 등장 배경",
    "핵심 개념과 도메인 배경",
    "내부 구조와 실제 동작 원리",
    "기술적 차별점과 대안 비교",
    "실제 활용 시나리오와 구체적 예시",
    "보안·안전·사회적 영향",
    "한계와 도입 전 검토사항",
    "프로젝트의 성숙도와 유지보수",
    "종합 평가와 추천 대상",
]
LONG_FORM_GUIDANCE = """
[글의 목표와 분량]
- 전체 본문은 최소 6,500자 이상. 각 섹션은 600~1,000자 이상을 목표로 하며, 주제에 따라 더 길어져도 된다.
- 짧은 요약이 아니라 독자가 배경과 원리부터 기술적 의미와 한계까지 이해할 수 있는 심층 분석 글을 작성한다.
- 설치법과 CLI 예시는 글의 일부일 뿐이다. README의 설치 절차를 길게 옮겨 분량을 채우지 않는다.
- 저장소에서 확인된 사실, 코드에서 직접 관찰한 사실, 일반적인 배경지식을 구분한다. 프로젝트 고유 기능은 저장소 근거가 있어야 한다.
- 근거 자료에 없는 숫자, 성능 벤치마크, 지원 플랫폼, 취약점, 내부 구현은 만들어내지 않는다. 자료가 부족하면 확인 불가라고 명시한다.

[분석 깊이]
1. 프로젝트가 등장한 문제 배경을 설명한다. 기존 방식의 작동 방식과 비용·불편·한계, 해당 프로젝트 유형이 필요한 이유를 다룬다.
2. 도메인의 기본 개념을 독자 눈높이에서 정의한다. 역공학 프로젝트라면 역공학과 디컴파일·디스어셈블의 차이, 소스 복구의 한계, 정적·동적 분석을 설명한다.
3. README만 반복하지 말고 저장소 트리와 실제 구현 파일을 활용해 구성요소, 데이터 흐름, 에이전트/도구 호출 경계, 외부 의존성, 실패 지점을 설명한다. 근거 파일 경로를 표시한다.
4. 전통적 도구나 대안과 비교할 때 역할, 자동화 수준, 필요한 환경, 사람의 개입 지점, 결과 검증 가능성을 구분한다. 근거 없이 우월하다고 단정하지 않는다.
5. 현실적인 활용 시나리오를 구체적으로 설명한다. 사용자가 어떤 입력을 넣고 어떤 결과를 얻으며 어떻게 검증해야 하는지 다룬다.
6. 보안·사회적 영향은 양면을 다룬다. 방어적 활용(악성코드 분석, 취약점 연구, 사고 대응, 공급망 검토)과 오용(무단 분석, 지식재산권 침해, 취약점 악용)을 구분하고 권한 및 격리 환경을 강조한다. 프로젝트에 확인되지 않은 취약점이 있다고 주장하지 않는다.
7. 라이선스·개인정보·비밀정보·실행 권한·외부 엔진 설치 등 도입 리스크를 분석한다. SPDX 태그만으로 상업적 이용 가능성을 단정하지 않는다.
8. 마지막에는 유용한 대상, 적합하지 않을 수 있는 대상, 도입 전 검증 항목을 구체적으로 제안한다.

[문체]
- 자연스러운 한국어 기술 블로그 문체. 같은 결론 반복이나 과장된 수식어로 분량을 늘리지 않는다.
- 핵심 용어는 처음 나올 때 쉬운 정의를 붙이고, 원인→작동 방식→의미→한계의 논리로 전개한다.
- 기술적 주장에는 저장소 파일 경로나 Markdown 링크를 제시하고 마지막에 실제 참고한 자료를 정리한다.
- 설치 명령은 필요한 만큼만 소개하고, 분량 대부분을 배경·설계·차별점·영향·한계 분석에 사용한다.
- 자료에 없는 기능은 추정으로 포장하지 않는다. 일반적인 도메인 설명은 '일반적으로'라고 구분한다.
"""

def _gather_candidates() -> list:
    payload = discover_github_candidates()
    candidates = []
    seen = set()
    # 사람이 고르는 프롬프트 없이 Scout가 자동 선택하도록 최근 활동 후보를 먼저 전달합니다.
    for item in payload.get("trending", []) + payload.get("popular", []):
        link = (item.get("link") or "").rstrip("/")
        if link and link.casefold() not in seen:
            seen.add(link.casefold())
            candidates.append(item)
    return candidates[:36]


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
        "후보 중 기술적 배경과 내부 동작을 분석할 자료가 충분하고 설명할 문제와 차별점이 있는 프로젝트를 "
        "자동으로 하나 선택한다. 이미 다룬 저장소는 후보 단계에서 제외된다. README 요약만으로 끝날 프로젝트보다 "
        "코드·문서·아키텍처 근거가 확인되는 프로젝트를 우선한다. 별점만 보지 말고 분야 다양성, 실용성, "
        "설명 가능성, 자료 접근성을 고려한다."
    ),
    writer_role="시니어 오픈소스 리서처이자 기술 블로그 저자",
    writer_goal=(
        "README를 다시 쓰는 데 그치지 않고 문제 배경, 핵심 개념, 실제 코드 구조, 차별점, 보안·사회적 영향, "
        "한계까지 독자가 이해하는 장문의 분석 글을 작성한다"
    ),
    writer_backstory=(
        "여러 분야의 오픈소스를 검토하는 개발자이자 기술 저술가. README와 저장소 파일을 교차 확인하고, "
        "일반적인 도메인 지식과 프로젝트에서 확인된 사실을 분리한다. 홍보 대신 원리와 근거를 설명하며 "
        "기술의 유용성과 오용 가능성을 균형 있게 다룬다."
    ),
    reviewer_role="기술 리서치 편집자 및 사실 검증자",
    reviewer_goal="장문 글의 깊이, 근거, 독창성, 기술적 정확성과 책임 있는 보안 서술을 검수한다",
    reviewer_checklist=(
        "본문이 최소 6500자 이상인가, README 설치 안내 재진술에 그치지 않는가, 문제 배경과 핵심 개념을 "
        "설명하는가, 실제 파일을 바탕으로 구조와 데이터 흐름을 분석하는가, 차별점과 대안을 근거 중심으로 "
        "비교하는가, 일반론과 저장소에서 확인한 사실을 구분하는가, 근거 없는 별점·기능·취약점·성능 수치를 "
        "만들지 않았는가, 보안 이중용도와 합법적 사용을 균형 있게 다루는가, 라이선스와 유지보수 판단에 "
        "불확실성을 명시하는가, 실제 참고한 공식 자료 링크가 있는가"
    ),
    build_context=_build_context,
    category_prefix_en="[Open Source Analysis]",
    section_names_en=(
        "Problem and Background", "Domain Concepts", "Internal Architecture and How It Works",
        "Technical Differentiators and Alternatives", "Practical Scenarios and Examples",
        "Security, Safety, and Societal Impact", "Limitations and Adoption Considerations",
        "Project Maturity and Maintenance", "Overall Assessment and Who Should Use It",
    ),
    min_section_chars=450,
    min_total_chars=6500,
    max_rounds=6,
    long_form_guidance=LONG_FORM_GUIDANCE,
    extra_writer_rules=(
        "- 설치 명령은 핵심 사용 흐름을 이해하는 데 필요한 정도로만 다룰 것\n"
        "- README 외에 전달된 코드·설정·문서 파일을 활용하고 파일 경로를 근거로 제시할 것\n"
        "- 도메인 배경과 프로젝트 고유 기능을 혼동하지 말 것\n"
        "- 출처 링크를 확인 가능한 Markdown 링크로 작성할 것\n"
        "- 별점이나 최근 업데이트를 품질·보안성의 증거로 사용하지 말 것"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
