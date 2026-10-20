"""
트러블슈팅 소재 수집 — GitHub 이슈 / StackOverflow
========================================================
파이썬이 먼저 실행해서 후보 목록(텍스트)을 만들고, 그걸 그대로 프롬프트에
박아 넣습니다. 에이전트에게 검색 툴 호출을 직접 맡기지 않는 이유는 로컬/소형
모델이 "툴 호출 -> 결과 반영" 왕복에서 자주 실패하기 때문입니다.

네트워크 실패는 전부 조용히 빈 리스트로 폴백합니다 — 소스 하나가 막혀도
파이프라인 전체가 죽지 않게.

각 후보/상세 정보에는 raw_body(이미지 추출용 원문)와 author(출처 표기용)를
같이 담아둡니다 — sources/images_capture.py가 이걸 가지고 실제 스크린샷을
다운로드합니다.
"""

import os
import html
import re
import time
import random
import datetime
import urllib.parse

from bs4 import BeautifulSoup

from sources import net

from sources.registry import (
    TROUBLESHOOTING_GITHUB_QUERY, TROUBLESHOOTING_MAX_AGE_YEARS,
    TROUBLESHOOTING_SEEDS, TROUBLESHOOTING_MIN_SCORE, TROUBLESHOOTING_EXCLUDED_TAGS,
    TROUBLESHOOTING_SEEDS_PER_RUN, TROUBLESHOOTING_PER_SEED,
)


def _get_json(url: str, headers: dict | None = None, timeout: int = 12):
    """실패하면 원인을 화면에 출력하고 None (sources/net.py 참고)."""
    return net.get_json(url, headers=headers, timeout=timeout)


def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _strip_html(s: str) -> str:
    """StackOverflow HTML -> 텍스트. <pre>는 ``` 코드블록으로, <code>는 `백틱`으로 바꾸고 HTML 엔티티
    (&quot; &lt; 등)를 풀어준다. 그렇지 않으면 코드가 &lt;...&gt;로 남아서 Writer 컨텍스트가 지저분해진다."""
    if not s:
        return ""
    soup = BeautifulSoup(s, "html.parser")
    for pre in soup.find_all("pre"):
        pre.replace_with("\n```\n" + pre.get_text().strip("\n") + "\n```\n")
    for code in soup.find_all("code"):
        code.replace_with(f"`{code.get_text()}`")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(["p", "li", "h1", "h2", "h3", "blockquote"]):
        tag.append("\n")
    return re.sub(r"\n{3,}", "\n\n", soup.get_text()).strip()


def _unescape(s):
    """StackExchange API는 제목/이름을 HTML 엔티티로 인코딩해서 준다(&quot; 등)."""
    return html.unescape(s) if isinstance(s, str) else s


def github_issue_common_errors(limit: int = 6) -> list:
    """제목에 error가 들어가고 댓글이 많이 달린 이슈 = 여러 사람이 실제로
    부딪힌 문제일 가능성이 높음."""
    since = (datetime.date.today() - datetime.timedelta(days=365 * TROUBLESHOOTING_MAX_AGE_YEARS)).isoformat()
    url = (
        "https://api.github.com/search/issues"
        f"?q={TROUBLESHOOTING_GITHUB_QUERY}+created:>{since}&sort=reactions&order=desc&per_page={limit}"
    )
    data = _get_json(url, headers=_github_headers())
    if not data:
        return []
    out = []
    for item in data.get("items", []):
        if not item.get("title"):
            continue
        if (item.get("user") or {}).get("type") == "Bot":
            continue
        raw_body = item.get("body") or ""
        out.append({
            "source": "GitHubIssue",
            "title": item.get("title", ""),
            "signal": f"💬{item.get('comments', 0)}",
            "link": item.get("html_url"),
            "body_excerpt": raw_body[:1200],  # LLM 컨텍스트용 (에러 원문이 잘리지 않을 정도로)
            "raw_body": raw_body,              # 이미지 추출용 (원문 그대로)
            "author": (item.get("user") or {}).get("login"),
            "meta": "{} · {} · {}".format(
                (item.get("repository_url") or "").split("/repos/")[-1] or "repo?",
                (item.get("created_at") or "")[:4] or "연도?",
                item.get("state", ""),
            ),
        })
    return out


def _stackexchange_get(url: str) -> list:
    key = os.getenv("STACKEXCHANGE_KEY")
    if key:
        url += f"&key={key}"
    data = _get_json(url, headers={"Accept": "application/json"})
    return (data or {}).get("items", [])


def stackoverflow_common_errors(limit: int = 6) -> list:
    """채택 답변이 있는 'error' 질문 — 원인+해결이 둘 다 확보되는 소재."""
    fromdate = int(time.time()) - 365 * 24 * 3600 * TROUBLESHOOTING_MAX_AGE_YEARS
    url = (
        "https://api.stackexchange.com/2.3/search/advanced"
        "?order=desc&sort=hot&q=error&accepted=True&answers=1"
        f"&fromdate={fromdate}&site=stackoverflow&pagesize={limit}&filter=withbody"
    )
    items = _stackexchange_get(url)
    out = []
    for item in items:
        if not item.get("title"):
            continue
        raw_body = item.get("body") or ""  # StackExchange filter=withbody는 HTML로 줌
        out.append({
            "source": "StackOverflow",
            "title": item.get("title", ""),
            "signal": f"👀{item.get('view_count', 0)}",
            "link": item.get("link"),
            "body_excerpt": _strip_html(raw_body)[:1200],
            "raw_body": raw_body,
            "author": (item.get("owner") or {}).get("display_name"),
            "meta": "StackOverflow · {} · score {}".format(
                datetime.datetime.fromtimestamp(item.get("creation_date", 0)).year if item.get("creation_date") else "연도?",
                item.get("score", "?"),
            ),
        })
    return out


def _title_matches_seed(title: str, seed: str) -> bool:
    """q 검색은 본문/답변에 단어만 들어 있어도 걸려서 에러와 무관한 인기 질문이 섞인다
    (실제로 'What does if __name__ == "__main__" do?'가 나왔음). 시드의 핵심 단어가 제목에
    60% 이상 들어 있는 질문만 인정한다."""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9_]{4,}", seed)]
    if not words:
        return True
    tl = title.lower()
    return sum(1 for w in words if w in tl) / len(words) >= 0.6


def stackoverflow_for_seed(seed: str, limit: int = 4) -> list:
    """시드(에러 메시지/증상)로 검색 — 파이썬 태그, 채택 답변 있음, 추천 수 높은 순.
    흔하고 검증된 Q&A만 나오게 하는 용도라 연도 제한은 두지 않음(파이썬 에러는 시간이
    지나도 유효한 경우가 대부분이고, 파이썬2 글은 태그로 제외)."""
    params = {
        "order": "desc", "sort": "votes", "q": seed, "accepted": "True", "answers": "1",
        "tagged": "python", "nottagged": TROUBLESHOOTING_EXCLUDED_TAGS,
        "min": str(TROUBLESHOOTING_MIN_SCORE),
        "site": "stackoverflow", "pagesize": "20", "filter": "withbody",
    }
    url = "https://api.stackexchange.com/2.3/search/advanced?" + urllib.parse.urlencode(params)
    out = []
    for item in _stackexchange_get(url):
        title = _unescape(item.get("title", ""))
        if not title or not _title_matches_seed(title, seed):
            continue
        if len(out) >= limit:
            break
        raw_body = item.get("body") or ""
        year = datetime.datetime.fromtimestamp(item["creation_date"]).year if item.get("creation_date") else "연도?"
        out.append({
            "source": "StackOverflow",
            "title": title,
            "signal": f"👍{item.get('score', '?')} 👀{item.get('view_count', 0)}",
            "link": item.get("link"),
            "body_excerpt": _strip_html(raw_body)[:1500],
            "raw_body": raw_body,
            "author": _unescape((item.get("owner") or {}).get("display_name")),
            "meta": f"StackOverflow · {year} · score {item.get('score', '?')} · seed: {seed}",
            "seed": seed,
        })
    return out


def stackoverflow_seed_candidates() -> list:
    """시드 목록에서 무작위로 몇 개를 골라 후보를 모은다 (매번 다른 에러가 나오도록)."""
    seeds = random.sample(TROUBLESHOOTING_SEEDS, k=min(TROUBLESHOOTING_SEEDS_PER_RUN, len(TROUBLESHOOTING_SEEDS)))
    out, seen = [], set()
    for seed in seeds:
        for c in stackoverflow_for_seed(seed, limit=TROUBLESHOOTING_PER_SEED):
            if c["link"] not in seen:
                seen.add(c["link"])
                out.append(c)
    return out


# =====================================================================
# 선택된 후보의 "해결까지 포함한" 상세 정보 가져오기 — Scout가 하나를 고른 뒤,
# Writer에게 줄 컨텍스트를 채우는 용도 (질문/이슈 본문만으로는 해결책이 없는
# 경우가 많아서, 채택 답변/코멘트까지 같이 가져옵니다)
# =====================================================================
def stackoverflow_answer_detail(question_link: str, max_chars: int = 2500) -> dict:
    """반환: {"text": LLM용 요약 텍스트, "raw_body": 이미지 추출용 원문 HTML, "author": str|None}"""
    empty = {"text": "", "raw_body": "", "author": None}
    m = re.search(r"stackoverflow\.com/questions/(\d+)", question_link or "")
    if not m:
        return empty
    qid = m.group(1)
    url = (
        f"https://api.stackexchange.com/2.3/questions/{qid}/answers"
        f"?order=desc&sort=votes&site=stackoverflow&filter=withbody"
    )
    items = _stackexchange_get(url)
    if not items:
        return empty
    accepted = next((a for a in items if a.get("is_accepted")), items[0])
    raw_body = accepted.get("body", "")
    return {
        "text": _strip_html(raw_body)[:max_chars],
        "raw_body": raw_body,
        "author": _unescape((accepted.get("owner") or {}).get("display_name")),
    }


def github_issue_comments_detail(issue_link: str, limit: int = 5, max_chars: int = 1500) -> dict:
    """반환: {"text": LLM용 요약 텍스트, "raw_body": 이미지 추출용 원문(코멘트 전체 결합), "author": str|None(첫 코멘트 작성자)}"""
    empty = {"text": "", "raw_body": "", "author": None}
    m = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_link or "")
    if not m:
        return empty
    owner, repo, number = m.groups()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments?per_page={limit}"
    data = _get_json(url, headers=_github_headers())
    if not data:
        return empty
    bodies = [(c.get("body") or "") for c in data[:limit]]
    combined_raw = "\n---\n".join(bodies)
    combined_text = "\n---\n".join(b[:400] for b in bodies)
    first_author = (data[0].get("user") or {}).get("login") if data else None
    return {"text": combined_text[:max_chars], "raw_body": combined_raw, "author": first_author}
