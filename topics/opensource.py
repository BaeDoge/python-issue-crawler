"""심층 장문 오픈소스 분석 주제.

후보 선정은 topics._common.run_topic의 Scout 에이전트가 자동 수행합니다.
"""
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
- 전체 본문은 최소 6,500자 이상으로 작성한다. 각 섹션은 최소 600~1,000자 정도를 목표로 하며, 주제에 따라 더 길어져도 된다.
- 알고리즘 풀이처럼 짧은 요약을 쓰지 말고, 독자가 처음 접하는 분야라도 배경과 용어부터 이해할 수 있는 기술 분석 칼럼으로 작성한다.
- 설치법이나 CLI 예시는 글의 일부일 뿐이다. README에 있는 설치 절차를 길게 옮기는 방식으로 분량을 채우지 않는다.
- 참고 자료에서 확인 가능한 사실, 코드에서 직접 관찰한 사실, 일반적인 배경지식을 명확히 구분한다. 프로젝트 고유 기능이라고 단정하려면 저장소 자료에 근거가 있어야 한다.
- 근거 자료에 없는 숫자, 성능 벤치마크, 지원 플랫폼, 취약점, 내부 구현은 만들어내지 않는다. 자료가 부족하면 확인 불가라고 명시한다.

[분석 깊이]
1. 프로젝트가 등장한 문제 배경을 설명한다. 기존 방식은 어떻게 작동하고 어떤 비용·불편·한계가 있었는지, 왜 이 프로젝트 유형이 필요한지 설명한다.
2. 도메인의 기본 개념을 독자 눈높이에서 정의한다. 예를 들어 역공학 프로젝트라면 역공학과 디컴파일·디스어셈블의 차이, 소스 코드 복구의 한계, 정적/동적 분석의 차이를 설명한다.
3. README 문구를 되풀이하지 말고, 저장소 트리와 실제 구현 파일을 활용해 구성요소, 데이터 흐름, 에이전트/도구 호출 경계, 외부 의존성, 실패 지점이 어떻게 연결되는지 설명한다. 코드에서 확인한 근거 파일 경로를 함께 표시한다.
4. 무엇이 실제 차별점인지 비교한다. 전통적 도구나 대안과 비교할 때 역할, 자동화 수준, 필요한 환경, 사람이 개입하는 지점, 결과의 검증 가능성을 구분한다. 근거가 없으면 우월하다고 단정하지 않는다.
5. 현실적인 활용 시나리오를 구체적으로 풀어 쓴다. 어떤 사람이 어떤 입력을 넣고, 어떤 결과를 얻으며, 그 결과를 어떻게 검증해야 하는지 설명한다.
6. 보안과 사회적 영향은 양면을 다룬다. 방어적 활용(악성코드 분석, 취약점 연구, 사고 대응, 공급망 검토)과 오용 가능성(무단 분석, 지식재산권 침해, 취약점 악용)을 구분하고, 합법적 권한과 격리된 실험 환경을 강조한다. 특정 프로젝트에서 확인되지 않은 취약점이 있다고 주장하지 않는다.
7. 라이선스·개인정보·비밀정보·실행 권한·외부 엔진 설치 등 실제 도입 리스크를 분석한다. 라이선스는 SPDX 태그만으로 결론 내리지 말고 원문 LICENSE 검토가 필요하다고 설명한다.
8. 마지막에는 프로젝트가 특히 유용할 사람, 적합하지 않을 수 있는 사람, 먼저 검증할 항목을 구체적으로 정리한다.

[문체와 구성]
- 자연스러운 한국어 기술 블로그 문체로 작성한다. 같은 결론을 반복하거나 과장된 수식어로 분량을 늘리지 않는다.
- 핵심 용어는 처음 나올 때 쉬운 정의를 붙이고, 필요한 경우 짧은 비유나 예시를 활용한다.
- 각 섹션은 단순 목록만 나열하지 말고 원인→작동 방식→의미→한계의 논리로 연결한다.
- 출처가 있는 기술적 주장에는 본문에서 저장소 파일 경로 또는 Markdown 링크를 함께 제시한다. 마지막에 공식 저장소와 실제 참고한 파일 링크를 출처 목록으로 정리한다.
- README에 잘 정리된 설치 명령은 필요한 만큼만 소개하고, 본문 분량 대부분을 배경·설계·차별점·영향·한계 분석에 사용한다.
- 자료에 없는 기능은 추정으로 포장하지 않는다. 일반적인 도메인 설명은 '일반적으로'라고 구분한다.
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
        "후보 중에서 기술적 배경과 내부 동작을 분석할 자료가 충분하고, 독자에게 설명할 만한 구체적인 문제와 "
        "차별점이 있는 프로젝트를 자동으로 하나 선택한다. 이미 다룬 저장소는 후보 단계에서 제외된다. "
        "README 요약만으로 끝날 프로젝트보다 코드·문서·아키텍처 근거가 확인되는 프로젝트를 우선한다. "
        "단순히 별점이 높다는 이유만으로 선택하지 말고, 분야 다양성, 실용성, 설명 가능성, 자료 접근성을 고려한다."
    ),
    writer_role="시니어 오픈소스 리서처이자 기술 블로그 저자",
    writer_goal=(
        "저장소의 README를 다시 쓰는 데 그치지 않고, 프로젝트가 해결하는 문제와 배경, 핵심 개념, "
        "실제 코드 구조, 차별점, 보안·사회적 영향, 한계까지 독자가 이해하는 장문의 분석 글을 작성한다"
    ),
    writer_backstory=(
        "여러 분야의 오픈소스를 검토하는 개발자이자 기술 저술가. README와 저장소 파일을 교차 확인하고, "
        "일반적인 도메인 지식과 프로젝트에서 확인된 사실을 분리한다. 과장된 홍보 문구 대신 원리와 근거를 "
        "설명하며, 기술의 유용성과 오용 가능성을 균형 있게 다룬다."
    ),
    reviewer_role="기술 리서치 편집자 및 사실 검증자",
    reviewer_goal="장문 글의 깊이, 근거, 설명력, 독창성, 기술적 정확성과 책임 있는 보안 서술을 검수한다",
    reviewer_checklist=(
        "본문이 충분한 장문 분석인가(최소 6500자), README 설치 안내를 재진술하는 데 그치지 않는가, "
        "문제 배경과 핵심 개념을 독자가 이해할 수 있게 설명하는가, 수집한 실제 파일 경로를 바탕으로 "
        "구조와 데이터 흐름을 분석하는가, 프로젝트의 차별점과 기존 대안을 근거 중심으로 비교하는가, "
        "도메인 일반론과 저장소에서 확인한 사실을 구분하는가, 근거 없는 스타 수·지원 기능·취약점·성능 수치를 "
        "만들지 않았는가, 보안 이중용도와 합법적 사용 범위를 균형 있게 다루는가, 라이선스와 유지보수 판단에 "
        "불확실성을 명시하는가, 출처 링크가 실제 참고한 공식 자료로 연결되는가"
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
        "- README 외에 전달된 코드·설정·문서 파일의 내용을 활용하고 파일 경로를 근거로 제시할 것\n"
        "- 역공학, 보안, AI 등 도메인 배경을 설명하되 프로젝트 고유 기능과 일반적인 기술 설명을 혼동하지 말 것\n"
        "- 출처 링크를 확인 가능한 Markdown 링크로 작성하고, 마지막 섹션 또는 본문 말미에 참고 자료를 명시할 것\n"
        "- 저장소의 별점이나 최근 업데이트를 품질·보안성의 증거로 사용하지 말 것"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
