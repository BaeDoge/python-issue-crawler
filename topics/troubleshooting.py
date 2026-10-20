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
from sources.registry import TROUBLESHOOTING_USE_GITHUB, BLOG_MAX_ARTICLES
from sources.web import (
    stackoverflow_seed_candidates, github_issue_common_errors,
    stackoverflow_answer_detail, github_issue_comments_detail,
)
from sources.blogs import blog_references
from sources.images_capture import capture_images
from topics._common import TopicSpec, run_topic

KEY = "troubleshooting"
LABEL = "코드 트러블슈팅"
SECTION_NAMES = ["현상", "원인", "해결 방법", "다른 해결 방법", "추가 참고사항"]
MIN_ANSWER_CHARS = 80   # 답변 본문이 이보다 짧으면 해결 단서가 없다고 보고 건너뜀


def _gather_candidates() -> list:
    candidates = stackoverflow_seed_candidates()
    if TROUBLESHOOTING_USE_GITHUB:
        candidates += github_issue_common_errors(limit=5)
    return candidates


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

    parts = [f"제목: {chosen['title']}", f"출처: {link}"]
    if chosen.get("meta"):
        parts.append(f"메타: {chosen['meta']}")
    if chosen.get("body_excerpt"):
        parts += ["", "질문/원문 내용:", chosen["body_excerpt"]]
    parts += ["", "채택 답변/코멘트(해결 단서):", answer_text]

    q_author, a_author = chosen.get("author"), detail.get("author")
    author = ", ".join(x for x in (f"{q_author}(질문)" if q_author else None,
                                   f"{a_author}(답변)" if a_author else None) if x) or None
    sources = [{"platform": platform, "title": chosen["title"], "url": link, "author": author}]

    image_items = [
        {"section": "현상", "raw_body": chosen.get("raw_body", ""), "source_url": link,
         "platform": platform, "author": q_author},
        {"section": "해결 방법", "raw_body": detail.get("raw_body", ""), "source_url": link,
         "platform": platform, "author": a_author},
    ]

    # 한국어 블로그 보조 자료 (실패해도 진행)
    third_party = False
    try:
        articles = blog_references(f"파이썬 {chosen['title']} 해결", max_articles=BLOG_MAX_ARTICLES)
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

    return {"context_text": "\n".join(parts), "source_url": link, "sources": sources,
            "images": images, "third_party": third_party}


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
        "단정하고 있지 않은가, 제목만 보고 어떤 에러인지 검색 가능한가"
    ),
    build_context=_build_context,
    code_required_sections=("현상", "해결 방법"),
    forbidden_phrases={"해결 방법": ("기다려야", "수정할 수 없", "해결할 수 없", "불가능합니다",
                                      "방법이 없", "코드 수정 불가")},
    extra_writer_rules=(
        "- 현상: 파이썬 버전/환경이 자료에 있으면 밝히고, 에러를 재현하는 최소 코드와 에러 출력 "
        "원문(traceback)을 각각 코드블록으로 그대로 넣을 것\n"
        "- 원인: 파이썬이 왜 이 에러를 내는지 동작 원리를 1~3문장으로\n"
        "- 해결 방법: 수정 전/후가 드러나는 실제 수정 코드를 코드블록으로 넣을 것(말로만 설명 금지)\n"
        "- 다른 해결 방법: 첫 번째와 접근이 다른 방법이나 다른 원인 케이스만(근본 해결 vs 방어적 처리, "
        "가상환경 문제 vs 패키지명 불일치처럼)\n"
        "- 추가 참고사항: 예방 팁이나 비슷한 에러 한두 가지\n"
        "- title은 검색할 때 쓸 만한 에러 이름을 포함할 것(예: \"[트러블슈팅] Python KeyError 해결\")"
    ),
)


def run() -> dict:
    return run_topic(SPEC)
