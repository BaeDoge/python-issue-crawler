"""Academic paper review topic."""
import history
from sources.papers import discover_candidates, build_context
from topics._common import TopicSpec, run_topic

KEY = "paper-review"
LABEL = "국내외 논문 리뷰"
SECTION_NAMES = [
    "논문과 연구 배경",
    "핵심 문제와 저자들의 주장",
    "제안 기술과 핵심 동작 원리",
    "실험 결과와 핵심 발견",
    "연결된 코드와 재현 방법",
    "기술적 시사점과 한계",
]
GUIDANCE = """
- 본문은 3,500~5,500자 수준으로 작성하되 근거가 부족한 내용을 만들지 않는다.
- 영어 초록과 본문의 핵심을 자연스러운 한국어로 번역·요약하고 전문 용어는 처음에 영문을 병기한다.
- 연구 문제, 기존 접근의 한계, 저자의 기여와 주장을 구분한다.
- 제안 기술의 구성 요소, 입력/출력, 처리 단계와 기존 기술과의 차이를 구체적으로 설명한다.
- 실험 수치에는 데이터셋, 비교 기준, 평가 지표를 함께 적고 원문에서 확인된 값만 인용한다.
- 초록만 확보했다면 논문 전체 실험, 표, 수치, 한계를 확인한 것처럼 쓰지 말고 확인 범위를 밝힌다.
- 공식 코드 저장소가 원문에서 확인된 경우에만 링크한다. 찾지 못하면 공개 구현을 확인하지 못했다고 적는다.
- 코드가 있으면 확인한 README/예제 범위에서 설치와 실행 흐름을 설명한다. 실행하지 않은 코드를 실행 검증했다고 쓰지 않는다.
- 저자의 주장, 논문에서 측정된 결과, 작성자의 해석을 분리한다.
- 마지막에는 기술적 의미, 실무 적용 가능성, 한계와 후속 연구 질문을 정리한다.
"""

def _gather_candidates() -> list:
    candidates = discover_candidates()
    unseen = [item for item in candidates if not history.is_used(KEY, item.get("link"))]
    print(f"[논문] 전체 {len(candidates)}편 중 미작성 {len(unseen)}편")
    return unseen

SPEC = TopicSpec(
    key=KEY, label=LABEL, category_prefix="[논문리뷰]", tag="Paper Review",
    section_names=SECTION_NAMES, gather_candidates=_gather_candidates,
    scout_criteria=(
        "국내 또는 해외 논문 중 AI/ML/데이터/소프트웨어/컴퓨터 분야 독자에게 유용하고 "
        "기술적 기여가 분명한 연구를 선택한다. 최신성, 초록의 구체성, 인용 수를 참고하되 "
        "인용 수만으로 품질을 단정하지 않는다. 대한민국 기관 소속 저자가 있으면 국내 연구로 표시한다. "
        "목록에 없는 논문은 선택하지 말 것."
    ),
    writer_role="학술 논문 기술 리뷰어",
    writer_goal="논문을 한국어로 번역·해설하고 핵심 기술과 시사점을 정확하게 설명한다",
    writer_backstory="AI와 컴퓨터 과학 논문을 실무 개발자 관점에서 해설하며 저자 주장, 실험 결과, 리뷰어 해석을 구분한다.",
    reviewer_role="학술 논문 사실 검증 편집자",
    reviewer_goal="논문 주장, 기술 설명, 실험 결과와 코드 링크가 원문 근거와 일치하는지 검토한다",
    reviewer_checklist=(
        "제목/저자/발행 정보가 일치하는가, 초록 번역이 정확한가, 저자 주장과 실험 결과 및 해석이 구분되는가, "
        "제안 기술을 근거 없이 지어내지 않았는가, 수치·데이터셋·비교 기준이 근거에 있는가, 코드 링크를 만들지 않았는가, "
        "초록만 읽고 전체 논문을 읽은 것처럼 쓰지 않았는가, 한계와 적용 조건을 다루는가"
    ),
    build_context=build_context,
    category_prefix_en="[Paper Review]",
    section_names_en=(
        "Paper and Research Background", "Core Problem and Authors' Claims",
        "Proposed Method and Key Mechanisms", "Experiments and Main Findings",
        "Related Code and Reproduction", "Technical Implications and Limitations",
    ),
    min_section_chars=180, max_rounds=3, min_total_chars=1800,
    long_form_guidance=GUIDANCE,
    extra_writer_rules=(
        "- 제목은 [논문리뷰]로 시작하고 논문의 핵심 기술/주제를 포함할 것\n"
        "- 국내/해외 구분은 제공된 저자 소속 메타데이터만 따를 것\n"
        "- 논문에 없는 수식, 수치, 코드 경로를 만들지 말 것\n"
        "- 원문, DOI, 초록, 공개 PDF, 코드 저장소 링크를 출처에 남길 것"
    ),
)

def run() -> dict:
    return run_topic(SPEC)
