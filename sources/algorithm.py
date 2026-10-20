"""
알고리즘 문제 소재 수집 — LeetCode
========================================================================
⚠️ 백준(acmicpc.net)이 2026년 4월 서비스를 종료했습니다(이후 데이원컴퍼니가
인수해 재개를 발표했지만, 같은 날 개인정보 유출 공지도 함께 나와 안정적으로
스크래핑할 수 있는 상태인지 불확실합니다). 그래서 이 파이프라인은 LeetCode를
씁니다 — 공식 문서화된 API는 아니지만, 수많은 오픈소스 도구가 쓰는 공개
GraphQL 엔드포인트(leetcode.com/graphql)로 로그인 없이 문제 목록과 지문을
가져올 수 있고, 서비스 자체도 훨씬 안정적입니다.

문제는 영어입니다 — Writer가 한국어로 번역/설명하도록 프롬프트에 명시했습니다
(topics/algorithm.py 참고). "리트코드 OOO 풀이"는 한국 개발 블로그에서도 흔한
장르라 자연스럽습니다.

⚠️ LeetCode가 그래프QL 엔드포인트 접근을 더 막으면(예: Cloudflare 챌린지)
이 모듈이 빈 결과만 반환할 수 있습니다. 그 경우 registry.py의
ALGORITHM_FALLBACK_SLUGS만으로 동작하게 되니, 주기적으로 문제가 잘 가져와지는지
확인해주세요.
"""

import random
import re

import requests

from sources import net

from sources.registry import ALGORITHM_DIFFICULTY, ALGORITHM_FALLBACK_SLUGS

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"

_SESSION = None


def _session():
    """브라우저처럼 먼저 사이트를 한 번 열어 쿠키(csrftoken)를 받은 세션. 쿠키 없이 GraphQL만
    두드리면 차단되는 경우가 있어서 넣었습니다(실패해도 그냥 진행)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        net.request("GET", "https://leetcode.com/problemset/", session=_SESSION, timeout=10, quiet=True, record=False)
    return _SESSION


def _graphql(query: str, variables: dict, timeout: int = 15):
    s = _session()
    headers = {"Content-Type": "application/json", "Referer": "https://leetcode.com/problemset/",
               "Origin": "https://leetcode.com"}
    token = s.cookies.get("csrftoken")
    if token:
        headers["x-csrftoken"] = token
    data = net.post_json(LEETCODE_GRAPHQL, {"query": query, "variables": variables},
                         headers=headers, timeout=timeout, session=s)
    if not data:
        return None
    if data.get("errors"):
        msg = str(data["errors"][0].get("message", data["errors"]))[:200]
        print(f"[LeetCode GraphQL 오류] {msg}")
        return None
    return data.get("data")


_LIST_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
    total: totalNum
    questions: data {
      difficulty
      frontendQuestionId: questionFrontendId
      paidOnly: isPaidOnly
      title
      titleSlug
      topicTags { name }
    }
  }
}
"""

_QUESTION_QUERY = """
query questionContent($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    title
    titleSlug
    difficulty
    content
    exampleTestcases
    isPaidOnly
    topicTags { name }
  }
}
"""


def leetcode_candidates(limit: int = 6) -> list:
    """난이도 Easy/Medium 위주로 몇 개 가져온다. paidOnly(유료 전용) 문제는 제외."""
    candidates = []
    seen_slugs = set()
    skip = random.randint(0, 400)  # 매번 같은 앞쪽 문제만 나오지 않도록 무작위 오프셋
    for difficulty in ALGORITHM_DIFFICULTY:
        data = _graphql(_LIST_QUERY, {
            "categorySlug": "", "skip": skip, "limit": limit,
            "filters": {"difficulty": difficulty},
        })
        if not data:
            continue
        questions = data.get("problemsetQuestionList", {}).get("questions", [])
        for q in questions:
            if q.get("paidOnly") or q["titleSlug"] in seen_slugs:
                continue
            seen_slugs.add(q["titleSlug"])
            candidates.append({
                "source": "leetcode",
                "title": f"LeetCode {q['frontendQuestionId']} - {q['title']}",
                "signal": q.get("difficulty"),
                "link": f"https://leetcode.com/problems/{q['titleSlug']}/",
                "title_slug": q["titleSlug"],
                "tags": [t["name"] for t in q.get("topicTags", [])][:3],
            })
        if len(candidates) >= limit:
            break

    if not candidates:
        for slug in random.sample(ALGORITHM_FALLBACK_SLUGS, k=min(limit, len(ALGORITHM_FALLBACK_SLUGS))):
            candidates.append({
                "source": "fallback_pool",
                "title": f"LeetCode - {slug}",
                "signal": None,
                "link": f"https://leetcode.com/problems/{slug}/",
                "title_slug": slug,
                "tags": [],
            })

    return candidates[:limit]


def _html_to_text(html: str) -> str:
    text = re.sub(r"<(br|/p|/div|/li)\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_leetcode_problem(title_slug: str) -> dict:
    """반환: {"title","difficulty","description","examples_raw","tags","url"}
    (description은 예제 포함 원문 전체를 텍스트로 변환한 것 — 예제를 따로
    파싱하기보다 전체를 LLM 컨텍스트로 주고 Writer가 알아서 정리하게 함)"""
    data = _graphql(_QUESTION_QUERY, {"titleSlug": title_slug})
    q = (data or {}).get("question")
    if not q or not q.get("content") or q.get("isPaidOnly"):
        return {"title": "", "difficulty": "", "description": "", "tags": [], "url": ""}

    return {
        "title": q.get("title", ""),
        "difficulty": q.get("difficulty", ""),
        "description": _html_to_text(q["content"]),
        "tags": [t["name"] for t in q.get("topicTags", [])],
        "url": f"https://leetcode.com/problems/{title_slug}/",
    }


def problem_context_text(title_slug: str) -> str:
    p = fetch_leetcode_problem(title_slug)
    if not p["description"]:
        return ""
    parts = [
        f"[LeetCode: {p['title']}] (난이도: {p['difficulty']})",
        f"원문: {p['url']}",
        "", "지문(영어 원문 — 한국어로 번역/요약해서 쓸 것):", p["description"],
    ]
    if p["tags"]:
        parts += ["", f"관련 태그(참고용): {', '.join(p['tags'])}"]
    return "\n".join(parts)
