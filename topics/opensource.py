"""GitHub 오픈소스 프로젝트 분석 노트."""
from __future__ import annotations

import inquirer

from sources.github_trending import discover_github_candidates, fetch_repository_context, print_candidates
from topics._common import TopicSpec, run_topic

KEY = "opensource"
LABEL = "GitHub 오픈소스 분석"
SECTION_NAMES = [
    "프로젝트 개요",
    "주요 기능과 기술 구조",
    "설치 및 사용 예시",
    "비슷한 프로젝트와 차이점",
    "장단점과 도입 시 고려사항",
    "유지보수 및 라이선스",
]


def _gather_candidates() -> list:
    payload = discover_github_candidates()
    print_candidates(payload)
    # 인기/최근 활동 목록을 합치고 저장소 URL 기준으로 중복을 제거합니다.
    candidates = []
    seen = set()
    for item in payload.get("popular", []) + payload.get("trending", []):
        if item.get("link") and item["link"] not in seen:
            seen.add(item["link"])
            candidates.append(item)
    if not candidates:
        return []
    # 터미널 선택창은 너무 길어지지 않도록 각 목록의 상위 15개만 노출합니다.
    choices_items = []
    for key in ("popular", "trending"):
        for item in payload.get(key, [])[:15]:
            if item.get("link") and all(old.get("link") != item["link"] for old in choices_items):
                choices_items.append(item)
    choices = [
        f"{item['title']} | ⭐ {item['stars']:,} | {item['group']} | "
        f"{'인기' if item['kind'] == 'popular' else '최근 활동'}"
        for item in choices_items
    ]
    selected = inquirer.list_input(
        "분석할 저장소를 직접 선택하세요",
        choices=choices + ["취소"],
    )
    if not selected or selected == "취소":
        return []
    return [choices_items[choices.index(selected)]]


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
        "사용자가 직접 선택한 GitHub 저장소를 분석한다. 선택한 프로젝트만 다루며, "
        "README와 수집된 저장소 메타데이터에 근거해 설명하고 확인할 수 없는 기능이나 구조는 추측하지 않는다."
    ),
    writer_role="오픈소스 프로젝트 분석가",
    writer_goal="개발자가 실제 도입 여부를 판단할 수 있도록 GitHub 프로젝트를 근거 중심으로 분석한다",
    writer_backstory=(
        "오픈소스 소프트웨어를 직접 검토해 기술 블로그에 소개하는 개발자. 홍보성 표현을 피하고 "
        "목적, 핵심 기능, 사용법, 대안, 제약, 유지보수 및 라이선스를 균형 있게 설명한다."
    ),
    reviewer_role="오픈소스 기술 검수자",
    reviewer_goal="분석 내용의 근거, 실용성, 라이선스 표현과 비교의 공정성을 검토한다",
    reviewer_checklist=(
        "공식 저장소 링크가 있는가, README에 없는 세부 기능이나 성능을 지어내지 않았는가, "
        "설치/사용 예시가 공식 문서와 부합하는가, 대안의 우열을 근거 없이 단정하지 않았는가, "
        "라이선스 태그만으로 상업적 이용 가능성을 단정하지 않았는가, 최근 업데이트와 별점이 품질 보증을 "
        "뜻하지 않는다고 설명하는가"
    ),
    build_context=_build_context,
    category_prefix_en="[Open Source Analysis]",
    section_names_en=(
        "Project Overview", "Key Features and Technical Structure", "Installation and Usage",
        "Alternatives and Differences", "Pros, Cons, and Adoption Considerations", "Maintenance and License",
    ),
    extra_writer_rules=(
        "- 사용 예시는 README에서 확인 가능한 설치/실행 방법만 사용할 것. 확인할 수 없으면 명령을 지어내지 말 것\n"
        "- 유지보수는 수집된 최근 push 날짜와 저장소 상태를 근거로 설명할 것\n"
        "- 라이선스 태그를 표시하고 원문 LICENSE 확인을 안내할 것\n"
        "- 대안 프로젝트는 이름만 나열하지 말고 확인 가능한 차이를 설명할 것\n"
        "- 자료에 없는 벤치마크 수치는 작성하지 말 것"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
