"""
코드 트러블슈팅 — 파이썬/라이브러리에서 흔하게 만나는 에러 (구조화 노트)
========================================================================
소재: sources/registry.py의 TROUBLESHOOTING_SEEDS(흔한 에러 목록)에서 무작위로 골라
StackOverflow의 "채택 답변 + 높은 추천 수" Q&A를 후보로 삼습니다. 해결책이 없는 글을
쓰게 되는 문제(예: "접근 권한 대기")를 막으려고 답변이 실제로 있는 후보만 씁니다.
보조: 티스토리/velog의 한국어 글(설명·스크린샷)을 참고 자료로 덧붙입니다(선택, 실패해도 진행).
섹션: 현상 / 원인 / 해결 방법 / 다른 해결 방법 / 추가 참고사항
출처는 글 맨 아래 "출처" 섹션에 한꺼번에 표기됩니다.
"""

from config import OUTPUT_DIR
import history
from sources.registry import TROUBLESHOOTING_USE_GITHUB, BLOG_MAX_ARTICLES
from sources.web import (
    stackoverflow_seed_candidates, github_issue_common_errors,
    stackoverflow_answer_detail, github_issue_comments_detail, _strip_html,
)
from sources import net
from sources.blogs import blog_references
from sources.images_capture import capture_images
from topics._common import TopicSpec, run_topic

KEY = "troubleshooting"
LABEL = "코드 트러블슈팅"
SECTION_NAMES = ["현상", "원인", "해결 방법", "다른 해결 방법", "추가 참고사항"]
MIN_ANSWER_CHARS = 80   # 답변 본문이 이보다 짧으면 해결 단서가 없다고 보고 건너뜀


def _gather_candidates() -> list:
    candidates = stackoverflow_seed_candidates(exclude_links=history.used_links(KEY))
    if TROUBLESHOOTING_USE_GITHUB:
        candidates += github_issue_common_errors(limit=5)
    return candidates


PANDAS_COW_DOC_URL = "https://pandas.pydata.org/docs/user_guide/copy_on_write.html"


def _load_official_reference(chosen: dict) -> dict:
    """Fetch current pandas CoW docs for pandas slice/chained-assignment topics."""
    haystack = " ".join(str(chosen.get(key, "")) for key in ("title", "seed", "meta", "body_excerpt")).casefold()
    is_pandas_topic = (
        "pandas" in haystack
        or "settingwithcopy" in haystack
        or "chained-assignment" in haystack
    )
    if not is_pandas_topic:
        return {}

    try:
        html_text = net.get_text(PANDAS_COW_DOC_URL, timeout=15, quiet=True)
    except Exception as exc:
        print(f"[pandas 공식 문서 수집 실패, 원문 자료로 계속 진행] {type(exc).__name__}: {str(exc)[:180]}")
        return {}
    if not html_text:
        print(f"[pandas 공식 문서 누락] {PANDAS_COW_DOC_URL} 응답이 비어 있습니다. 이번 글은 현재 버전 근거 없이 작성됩니다.")
        return {}

    clean = _strip_html(html_text)
    # The version history appears BEFORE the "Previous behavior" heading.
    # Start at the introductory CoW note so 1.5.0 / 2.0 / 2.1 / 3.0 are all retained.
    start = clean.find("Copy-on-Write is now the default")
    if start < 0:
        start = clean.find("Copy-on-Write was first introduced")
    if start < 0:
        print("[pandas 공식 문서 누락] 버전 안내 문구를 찾지 못했습니다. 이전 동작 설명만으로 현재 버전을 추정하지 않습니다.")
        return {}
    end = clean.find("Read-only NumPy arrays", start if start >= 0 else 0)
    if start < 0 or end <= start:
        print("[pandas 공식 문서 누락] Copy-on-Write 버전 안내 구간을 추출하지 못했습니다.")
        return {}
    excerpt = clean[start:end].strip()[:9000]
    if len(excerpt) < 300:
        print("[pandas 공식 문서 누락] 추출된 근거가 너무 짧아 검수 자료로 사용하지 않습니다.")
        return {}

    return {
        "platform": "pandas 공식 문서",
        "title": "Copy-on-Write (CoW)",
        "url": PANDAS_COW_DOC_URL,
        "text": excerpt,
    }


def _build_context(chosen: dict) -> dict:
    empty = {"context_text": "", "source_url": None}
    link = chosen.get("link", "")
    is_so = "stackoverflow.com" in link
    platform = "StackOverflow" if is_so else "GitHub"

    if is_so:
        detail = stackoverflow_answer_detail(link)
    elif "github.com" in link:
        detail = github_issue_comments_detail(link)
    else:
        return empty

    answer_text = detail["text"]
    if len(answer_text) < MIN_ANSWER_CHARS:
        return empty   # 해결 단서가 없는 후보는 쓰지 않음

    official_reference = _load_official_reference(chosen)
    parts = [f"제목: {chosen['title']}", f"출처: {link}"]
    if chosen.get("meta"):
        parts.append(f"메타: {chosen['meta']}")
    if chosen.get("body_excerpt"):
        parts += ["", "질문/원문 내용:", chosen["body_excerpt"]]
    parts += ["", "채택 답변/코멘트(해결 단서):", answer_text]
    if official_reference:
        parts += [
            "",
            f"[최신 공식 문서: {official_reference['title']}] ({official_reference['url']})",
            "아래 공식 문서는 StackOverflow 질문보다 최신일 수 있습니다. 버전별 동작 차이를 확인할 때 우선 근거로 사용하세요.",
            official_reference["text"],
        ]

    source_combined = "\n".join([
        str(chosen.get("title", "")),
        str(chosen.get("body_excerpt", "")),
        answer_text,
    ])
    is_pandas_copy_warning = (
        "pandas" in source_combined.casefold()
        and "settingwithcopywarning" in source_combined.casefold()
    )
    if is_pandas_copy_warning:
        source_note = (
            "원문 해석상 주의: StackOverflow 질문의 실제 연산은 df['quantity'] *= -1 이며 "
            "질문자는 pandas 0.16.2를 사용했다고 밝혔다. 질문에는 df 생성 과정이 나오지 않는다. "
            "댓글과 답변은 df가 상위 DataFrame에서 필터링된 슬라이스였을 가능성을 지적하고, "
            "독립된 부분 데이터가 목적이면 슬라이스를 만드는 시점에 .copy()를 적용하라고 설명한다. "
            "df[['quantity']] 자체가 원문 경고를 재현한다고 지어내지 말 것. "
            "상위 DataFrame을 수정하려면 original_df.loc[mask, 'quantity']에 직접 할당하고, "
            "독립된 부분 데이터가 목적이면 df = original_df.loc[mask].copy() 후 수정할 것. "
            "Copy-on-Write 도입/기본값 전환의 pandas 버전을 공식 문서와 일치시킬 것."
        )
        if official_reference:
            source_note += (
                "공식 문서는 Copy-on-Write가 1.5.0에서 처음 도입되었고, 2.0/2.1에서 지원이 확대되었으며, "
                "3.0에서 기본이자 유일한 모드가 되었다고 설명한다. 이 순서를 바꾸지 말 것."
            )
        else:
            source_note += (
                "현재 공식 문서를 가져오지 못했다. 따라서 Copy-on-Write의 최초 도입 버전이나 "
                "현재 기본값 전환 버전을 단정하지 말고, 버전별 동작은 확인되지 않았다고 명시하거나 생략할 것."
            )
        parts += ["", "[원문 기반 편집 메모 — 본문에 그대로 복사하지 말고 정확한 설명에 활용]", source_note]

    q_author, a_author = chosen.get("author"), detail.get("author")
    author = ", ".join(x for x in (f"{q_author}(질문)" if q_author else None,
                                   f"{a_author}(답변)" if a_author else None) if x) or None
    sources = [{"platform": platform, "title": chosen["title"], "url": link, "author": author}]
    if official_reference:
        sources.append({
            "platform": official_reference["platform"],
            "title": official_reference["title"],
            "url": official_reference["url"],
        })

    image_items = [
        {"section": "현상", "raw_body": chosen.get("raw_body", ""), "source_url": link,
         "platform": platform, "author": q_author},
        {"section": "해결 방법", "raw_body": detail.get("raw_body", ""), "source_url": link,
         "platform": platform, "author": a_author},
    ]

    # 한국어 블로그는 원문 질문/채택 답변과 오류 앵커가 맞는 자료만 보조로 사용한다.
    third_party = False
    blog_relevance_context = "\n".join([
        str(chosen.get("title", "")),
        str(chosen.get("body_excerpt", "")),
        answer_text,
    ])
    try:
        articles = blog_references(
            f"파이썬 {chosen['title']} 해결",
            max_articles=BLOG_MAX_ARTICLES,
            relevance_context=blog_relevance_context,
        )
    except Exception as e:  # 네트워크/파싱 어떤 이유든 블로그 때문에 전체가 멈추면 안 됨
        print(f"[블로그 참고 자료 수집 실패, 건너뜀] {e}")
        articles = []
    for n, art in enumerate(articles, 1):
        parts += ["", f"[한국어 블로그 참고 {n}: {art['platform']} - {art['title']}] (문장을 베끼지 말고 참고만)",
                  art["text"][:1800]]
        sources.append({"platform": art["platform"], "title": art["title"], "url": art["url"], "author": art["author"]})
        if art["image_urls"]:
            image_items.append({"section": "현상" if n == 1 else "해결 방법", "urls": art["image_urls"],
                                "source_url": art["url"], "platform": art["platform"], "author": art["author"]})
        third_party = True

    slug_hint = "".join(ch for ch in chosen["title"] if ch.isalnum())[:20].lower() or "note"
    images = capture_images(items=image_items, out_dir=OUTPUT_DIR / KEY / "images", slug_hint=slug_hint)

    # Give the Verifier the same primary evidence as the Writer.
    review_parts = [
        f"1차 출처 플랫폼: {platform}",
        f"1차 출처 제목: {chosen['title']}",
        f"1차 출처 URL: {link}",
    ]
    if chosen.get("meta"):
        review_parts.append(f"원문 메타데이터: {chosen['meta']}")
    if chosen.get("body_excerpt"):
        review_parts += ["원문 질문/이슈 본문:", chosen["body_excerpt"][:3000]]
    review_parts += ["채택 답변/해결 코멘트:", answer_text[:3500]]
    if official_reference:
        review_parts += [
            f"공식 문서: {official_reference['title']}",
            f"공식 문서 URL: {official_reference['url']}",
            "공식 문서 발췌:",
            official_reference["text"][:9000],
        ]
    elif is_pandas_copy_warning:
        review_parts += [
            "현재 공식 문서 조회 상태: pandas 공식 Copy-on-Write 문서를 가져오지 못했다.",
            "따라서 Copy-on-Write의 최초 도입 버전이나 현재 기본값 전환 버전에 대한 단정은 근거가 없다. 해당 주장은 생략하거나 확인되지 않았다고 표시한다.",
        ]
    review_context = "\n\n".join(review_parts)
    return {"context_text": "\n".join(parts), "source_url": link, "sources": sources,
            "images": images, "third_party": third_party, "review_context": review_context}


SPEC = TopicSpec(
    key=KEY,
    label=LABEL,
    category_prefix="[트러블슈팅]",
    tag="Troubleshooting",
    section_names=SECTION_NAMES,
    gather_candidates=_gather_candidates,
    scout_criteria=(
        "아래 후보는 파이썬 개발자들이 자주 만나는 에러에 대한 StackOverflow Q&A다(채택 답변 "
        "있음). 판단 기준: (1) 초중급 개발자가 흔하게 만나는 에러인가 (2) 원인과 해결이 명확하고 "
        "코드로 보여줄 수 있는가 (3) 특정 회사/서비스/개인 환경에만 해당하는 문제가 아닌가 "
        "(4) 파이썬 3 기준으로 지금도 유효한가(meta의 연도 참고) (5) 추천 수(signal)가 높을수록 우선."
    ),
    writer_role="파이썬 트러블슈팅 노트 작성자",
    writer_goal="주어진 자료를 바탕으로 현상-원인-해결 구조의 명확한 파이썬 에러 해결 노트를 작성한다",
    writer_backstory=(
        "파이썬 개발자들이 자주 겪는 에러를 현상-원인-해결 구조로 정리해 레퍼런스 문서처럼 "
        "제공하는 작성자. 장황한 설명 없이 핵심만, 실제로 따라 하면 해결되는 코드로 전달한다."
    ),
    reviewer_role="기술 문서 검수자",
    reviewer_goal="노트가 정확하고 실용적이며 발행 가능한 수준인지 검토한다",
    reviewer_checklist=(
        "현상에 에러 원문(그리고 가능하면 재현 코드)이 코드블록으로 있는가, 원인이 파이썬 동작 "
        "원리로 설명되는가, 해결 방법이 독자가 실제로 따라 할 수 있는 수정 코드인가(‘기다려야 "
        "한다’‘불가능하다’면 불합격), 다른 해결 방법이 첫 번째와 실제로 다른 접근/상황인가, "
        "참고 자료에 없는 사실을 지어내지 않았는가, 코드가 문법적으로 맞고 API 사용이 자료형에 "
        "맞는가(예: dict 키 확인에 getattr 사용은 오류), 원인이 확인되지 않았는데 summary가 "
        "단정하고 있지 않은가, 제목만 보고 어떤 에러인지 검색 가능한가. "
        "외부 라이브러리의 버전별 동작을 다룰 때 StackOverflow 작성 시기와 현재 공식 문서의 기준 버전을 구분했는가, "
        "공식 문서와 과거 Q&A가 충돌하면 두 동작을 구분해 설명했는가, "
        "환경 변수·PATH·레지스트리·권한·데이터를 변경하는 명령이 현재 세션용인지 영구 변경인지 "
        "분명히 구분했는가, 기존 설정 전체를 덮어쓰거나 삭제하는 위험한 명령을 무심코 권장하지 않았는가, "
        "원문 인용·오류 서명·재현 코드·원인·수정 코드가 숨김 근거 명세에서 서로 연결되고 실제 원문에 근거하는가, "
        "원문에 없는 변수명·속성명·버전·오류 원인을 추가하지 않았는가"
    ),
    build_context=_build_context,
    category_prefix_en="[Troubleshooting]",
    section_names_en=("Symptom", "Cause", "Solution", "Alternative Solutions", "Additional Notes"),
    code_required_sections=("현상", "해결 방법"),
    max_rounds=3,
    revision_guidance=(
        "트러블슈팅 수정 시 현상·원인·해결 방법을 서로 독립된 문단으로 취급하지 말고 하나의 재현 가능한 흐름으로 다시 대조할 것. "
        "검수자가 재현 코드와 해결 코드의 불일치를 지적했다면 기존 변수명을 억지로 보존하지 말고, 원문 질문/채택 답변에 실제로 나온 변수와 자료형부터 다시 확인할 것. "
        "원문에 없는 json, referenceElement 같은 변수나 업무 맥락을 새로 만들지 말 것. "
        "원문 코드를 단순화했다면 '최소 재현 예시'라고 표시하고, 그 예시가 같은 예외를 발생시키는지 확인할 것. "
        "각 해결 코드가 실제로 원인이 된 잘못된 연산을 제거하는지 설명할 것. "
        "pass만 실행하는 빈 반복문, 결과를 바꾸지 않는 코드, 목적이 설명되지 않은 keys() 순회는 해결책으로 제시하지 말 것. "
        "키로 사용할 값만 필요한지, 딕셔너리 전체 내용이 식별자여야 하는지 구분하고 각각의 해결책을 분리해서 설명할 것. "
        "외부 라이브러리의 버전별 동작은 원문 작성 시기와 제공된 공식 문서를 대조하고, 과거 동작과 현재 동작을 혼합하지 말 것. "
        "현재/최신이라는 표현은 공식 문서의 근거가 제공된 경우에만 사용할 것. "
        "Windows PATH를 영구 변경할 때 setx PATH \"%PATH%;...\"처럼 기존 PATH 전체를 다시 저장하도록 권하지 말 것. "
        "Windows 환경 변수 편집 화면에서 기존 Path 항목을 보존한 채 새 Scripts 경로를 별도 항목으로 추가하도록 안내할 것. "
        "현재 CMD 세션에만 적용하는 set PATH 명령과 영구 설정 절차를 혼동하지 말 것. "
        "pip 사용법을 설명할 때는 가능한 경우 python -m pip 또는 py -m pip를 우선 제시해 인터프리터와 pip의 연결을 명확히 할 것. "
        "환경 변수, 레지스트리, 파일 권한, 데이터베이스를 변경하는 명령은 변경 범위와 지속성을 설명하고, 기존 값을 보존하는 안전한 절차를 우선할 것. "
        "이 지침과 원문만으로 실제 해결책을 특정할 수 없으면 특정 사례를 지어내지 말고 조건부 선택지를 명확히 구분할 것. "
        "TROUBLESHOOTING_CHECKS의 source_quote와 shared_terms는 실제 원문에 있는 연속 구절과 식별자만 사용하고, 코드를 수정하면 블록 인덱스도 다시 계산할 것."
    ),
    forbidden_phrases={"해결 방법": ("기다려야", "수정할 수 없", "해결할 수 없", "불가능합니다",
                                      "방법이 없", "코드 수정 불가")},
    extra_writer_rules=(
        "- 현상: 파이썬 버전/환경이 자료에 있으면 밝히고, 에러를 재현하는 최소 코드와 에러 출력 "
        "원문(traceback)을 각각 코드블록으로 그대로 넣을 것\n"
        "- 첫 섹션 헤더(## 현상) 바로 앞에 TROUBLESHOOTING_CHECKS HTML 주석을 정확히 한 번 작성할 것. 게시물 본문에 노출되면 안 되는 내부 검증 명세다.\n"
        "- TROUBLESHOOTING_CHECKS JSON 형식 예시: <!-- TROUBLESHOOTING_CHECKS { \\"source_quote\\": \\"원문 질문/채택 답변에서 복사한 24자 이상의 연속 구절\\", \\"error_signature\\": \\"KeyError\\", \\"reproduction_block_index\\": 0, \\"fix_block_index\\": 0, \\"shared_terms\\": [\\"data\\"], \\"cause_terms\\": [\\"dictionary\\", \\"key\\"], \\"fix_terms\\": [\\"get\\"], \\"environment\\": {} } -->\n"
        "- source_quote는 제공된 StackOverflow 질문/채택 답변 또는 공식 문서에서 그대로 복사한 24자 이상 연속 구절이어야 하며 요약하거나 새로 만들지 말 것.\n"
        "- error_signature는 원문과 현상 섹션에 실제로 표시되는 예외명 또는 오류 메시지 일부를 정확히 지정할 것.\n"
        "- reproduction_block_index는 현상 섹션의 코드 펜스를 위에서부터 센 0 기반 인덱스, fix_block_index는 해결 방법 섹션의 코드 펜스 인덱스다. 오류 출력 블록과 실행 명령 블록을 포함해 모든 펜스를 센다.\n"
        "- shared_terms에는 원문 인용·재현 블록·수정 블록 모두에 실제로 등장하는 동일한 변수명/속성명/명령 토큰 1~3개만 넣을 것. 원문에 없는 json, referenceElement 같은 이름을 만들어 넣지 말 것.\n"
        "- cause_terms는 원인 섹션에 실제로 설명한 기술 키워드 1~3개, fix_terms는 해결 방법 코드 또는 명령에 실제로 포함된 조치 토큰 1~3개를 넣을 것.\n"
        "- environment에는 원문에 명시된 패키지/런타임 버전만 { 패키지명: 버전 }으로 기록하고, 원문에 버전이 없으면 빈 객체로 둘 것. 원문에 없는 최신 버전을 추정하지 말 것.\n"
        "- 원인: 파이썬이 왜 이 에러를 내는지 동작 원리를 1~3문장으로\n"
        "- 해결 방법: 수정 전/후가 드러나는 실제 수정 코드를 코드블록으로 넣을 것(말로만 설명 금지)\n"
        "- 다른 해결 방법: 첫 번째와 접근이 다른 방법이나 다른 원인 케이스만(근본 해결 vs 방어적 처리, "
        "가상환경 문제 vs 패키지명 불일치처럼)\n"
        "- 추가 참고사항: 예방 팁이나 비슷한 에러 한두 가지\n"
        "- title은 검색할 때 쓸 만한 에러 이름을 포함할 것(예: \"[트러블슈팅] Python KeyError 해결\")\n"
        "- 오류의 핵심 메시지는 <Callout type=\"warning\" title=\"오류 상황\">으로 짧게 강조할 수 있다.\n"
        "- 해결 절차가 2단계 이상이면 <Steps>와 <Step title=\"...\">를 사용해 순서를 보여준다.\n"
        "- 실제 실행 명령과 예상 출력을 구분해 <Terminal title=\"실행 명령\"> 안에 코드 블록으로 배치할 수 있다. 실행하지 않은 결과를 성공 로그처럼 꾸미지 않는다.\n"
        "- CMD, PowerShell, Bash 등 명령은 실제 셸 문법에 맞는 펜스 언어와 함께 제시하고, 셸을 혼용하지 말 것.\n"
        "- PATH나 환경 변수를 영구 변경할 때 기존 값을 통째로 덮어쓰는 명령을 제시하지 말 것. Windows는 환경 변수 편집 화면에서 새 항목을 추가하는 절차를 우선하고, 임시 세션 명령과 구분할 것.\n"
        "- pip를 설치하거나 실행할 때는 해당 Python 인터프리터와 연결된 python -m pip / py -m pip를 우선 제시할 것.\n"
        "- 레지스트리, 파일 권한, PATH, 데이터베이스 등 시스템 상태를 바꾸는 명령은 변경 대상·영향 범위·되돌리는 방법을 설명할 것.\n"
        "- 수정 전후 코드가 짧고 비교 가치가 있을 때만 <Compare>와 <ComparePanel>을 사용한다.\n"
        "- 마지막에 환경 확인 항목이 실제로 여러 개 있을 때만 <Checklist>를 사용한다.\n"
        "- 현상, 원인, 해결 방법의 예시 코드와 설명이 같은 변수·자료형·연산을 다루는지 서로 대조할 것.\n"
        "- 외부 라이브러리의 동작을 설명할 때 StackOverflow 질문의 작성 연도/환경과 현재 공식 문서의 버전 범위를 구분할 것.\n"
        "- 자료가 오래되었거나 버전 정보가 없으면 현재 버전에서도 동일하다고 단정하지 말 것.\n"
        "- 공식 문서가 과거 동작과 현재 동작의 차이를 설명하면 두 시기를 별도 문단으로 구분하고 각 예제 코드를 해당 버전에 맞출 것.\n"
        "- 원문에 없는 json/referenceElement 등 변수명을 임의로 만들지 말 것. 코드를 단순화하면 최소 재현 예시라고 밝힐 것.\n"
        "- 해결 코드에는 실제 수정 동작을 넣고, pass만 있는 빈 반복문이나 단순 keys() 순회를 해결책으로 제시하지 말 것.\n"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
