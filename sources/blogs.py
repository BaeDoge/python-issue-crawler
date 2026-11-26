"""
한국어 블로그(티스토리 / velog) 참고 자료 수집
========================================================================
선택된 에러에 대해 한국어로 정리된 블로그 글을 찾아서, 본문 텍스트(보조 컨텍스트)와
본문 이미지(스크린샷)를 가져옵니다. 글 자체를 복사하는 게 아니라 Writer가 자기 말로
다시 쓰는 참고 자료로만 쓰고, 출처는 글 맨 아래 "출처" 섹션에 일괄 표기됩니다.

검색 백엔드 (둘 중 되는 것을 씀):
1. Tavily — TAVILY_API_KEY가 .env에 있으면 사용. 무료 티어가 있고(월 1,000 크레딧,
   https://tavily.com), 도메인 지정 검색이 안정적입니다.
2. DuckDuckGo HTML — 키 없이 동작하지만 마크업이 바뀌면 깨질 수 있는 스크래핑입니다.

⚠️ 이 모듈은 제가 작업한 환경에서 실제 검색/페이지 접속을 못 해봐서, 아래 항목은
직접 돌려보셔야 확인됩니다: (1) 검색 결과가 실제로 나오는지, (2) 티스토리/velog 본문
추출이 잘 되는지. 실패하면 조용히 빈 결과를 돌려주고, 그 경우 노트는 StackOverflow
자료만으로 만들어집니다(파이프라인이 멈추지 않음).
"""

import os
import re
import unicodedata
import urllib.parse

from bs4 import BeautifulSoup

from sources import net

from sources.images_capture import filter_image_urls
from sources.registry import BLOG_DOMAINS

def _platform_of(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "tistory.com" in host:
        return "Tistory"
    if "velog.io" in host:
        return "Velog"
    return host or "블로그"


def _tavily_search(query: str, api_key: str, limit: int) -> list:
    data = net.post_json("https://api.tavily.com/search", {
        "api_key": api_key, "query": query, "max_results": limit,
        "search_depth": "basic", "include_domains": BLOG_DOMAINS,
    }, timeout=20)
    if not data:
        return []
    return [{"title": r.get("title", ""), "url": r["url"]} for r in data.get("results", []) if r.get("url")]


def _ddg_search(query: str, limit: int) -> list:
    site_filter = " OR ".join(f"site:{d}" for d in BLOG_DOMAINS)
    q = f"{query} ({site_filter})"
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    html = net.get_text(url, timeout=15, headers={"Accept-Language": "ko-KR,ko;q=0.9"})
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        # DuckDuckGo는 //duckduckgo.com/l/?uddg=<인코딩된 실제 URL> 형태로 감싸서 줌
        m = re.search(r"uddg=([^&]+)", href)
        real = urllib.parse.unquote(m.group(1)) if m else href
        if real.startswith("http") and any(d in real for d in BLOG_DOMAINS):
            out.append({"title": a.get_text(strip=True), "url": real})
        if len(out) >= limit:
            break
    if not out:
        text = re.sub(r'\\s+', ' ', html[:120])
        net.note_error(url, "DuckDuckGo가 검색 결과를 주지 않음(봇 차단 또는 마크업 변경). "
                            "안정적으로 쓰려면 .env에 TAVILY_API_KEY(무료)를 설정하세요. "
                            f"응답 앞부분: {text}")
    return out


def search_blog_posts(query: str, limit: int = 4) -> list:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if key:
        results = _tavily_search(query, key, limit)
        if results:
            return results
    return _ddg_search(query, limit)


# 본문 영역 후보 선택자 (티스토리 스킨은 제각각이라 여러 개를 시도하고, 못 찾으면 가장 긴 텍스트 블록을 씀)
_CONTENT_SELECTORS = [
    "div.tt_article_useless_p_margin", "div.contents_style", "div.entry-content",
    "div.article-view", "div#article-view", "article", "div.post-content",
    "div[class*=atom-one]", "div[class*=content]", "div[id*=content]",
]


def parse_article_html(html: str, url: str) -> dict:
    """페이지 HTML에서 제목/본문 텍스트/본문 이미지 URL을 추출한다 (네트워크 없이 테스트 가능하게 분리)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "iframe"]):
        tag.decompose()

    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title:
        title = soup.title.get_text(strip=True)

    author = None
    meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="og:site_name")
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()

    container = None
    for sel in _CONTENT_SELECTORS:
        found = soup.select(sel)
        if found:
            container = max(found, key=lambda el: len(el.get_text(strip=True)))
            if len(container.get_text(strip=True)) > 200:
                break
    if container is None or len(container.get_text(strip=True)) <= 200:
        blocks = soup.find_all(["div", "section", "main"])
        container = max(blocks, key=lambda el: len(el.get_text(strip=True)), default=soup)

    # 코드(<pre>)는 줄바꿈을 살리고, 나머지는 문단 단위로
    parts = []
    for el in container.find_all(["p", "pre", "h1", "h2", "h3", "li"]):
        txt = el.get_text("\n" if el.name == "pre" else " ", strip=True)
        if not txt:
            continue
        parts.append(f"```\n{txt}\n```" if el.name == "pre" else txt)
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    img_urls = []
    for img in container.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("http"):
            img_urls.append(src)

    return {
        "title": title, "url": url, "author": author, "platform": _platform_of(url),
        "text": text, "image_urls": filter_image_urls(img_urls, limit=4),
    }


def fetch_blog_article(url: str, max_chars: int = 3500) -> dict | None:
    html = net.get_text(url, timeout=15, headers={"Accept-Language": "ko-KR,ko;q=0.9"}, quiet=True)
    if not html:
        return None
    article = parse_article_html(html, url)
    if len(article["text"]) < 200:
        return None  # 본문 추출 실패(로그인 벽, 비공개 글, 구조 불일치)
    article["text"] = article["text"][:max_chars]
    return article



_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}|[가-힣]{2,}", re.I)
_ERROR_MARKER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*(?:Error|Warning|Exception)\b", re.I)
_TOPIC_STOP_WORDS = {
    "python", "파이썬", "pandas", "판다스", "dataframe", "데이터프레임",
    "해결", "방법", "오류", "에러", "문제", "사용", "관련", "대한",
    "how", "what", "when", "where", "with", "from", "into", "your",
    "this", "that", "the", "and", "for", "are", "was", "use", "using",
    "data", "frame", "column", "entire", "scalar",
}
_ERROR_ALIASES = {
    "settingwithcopywarning": (
        "settingwithcopywarning", "chained assignment", "chained_assignment",
        "copy-on-write", "copy on write", "view versus copy", "views versus copies",
        "슬라이스 복사본", "슬라이스 할당", "뷰와 복사본", "체이닝 할당", "연쇄 할당",
    ),
}


def _normalized_match_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^a-z0-9가-힣]+", "", value)


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return {token for token in _TOKEN_RE.findall(normalized) if token not in _TOPIC_STOP_WORDS}


def _issue_aliases(source_context: str) -> list[tuple[str, ...]]:
    aliases: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for marker in _ERROR_MARKER_RE.findall(source_context or ""):
        key = marker.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(_ERROR_ALIASES.get(key, (marker,)))
    return aliases


def is_relevant_blog_article(
    *, query: str, relevance_context: str = "", title: str = "", text: str = ""
) -> bool:
    """Reject pages that share only broad terms such as Python or DataFrame."""
    source_context = relevance_context.strip() or query
    candidate_text = f"{title}\n{text}"
    candidate_normalized = _normalized_match_text(candidate_text)
    aliases = _issue_aliases(source_context)

    if aliases:
        for alternatives in aliases:
            if not any(_normalized_match_text(item) in candidate_normalized for item in alternatives):
                return False
        return True

    source_tokens = _tokens(source_context)
    candidate_tokens = _tokens(candidate_text)
    overlap = source_tokens & candidate_tokens
    if len(overlap) < 2:
        return False
    return len(overlap) / max(1, min(len(source_tokens), 8)) >= 0.25


def blog_references(
    query: str,
    max_articles: int = 2,
    *,
    relevance_context: str = "",
) -> list:
    """Search, fetch and keep only pages relevant to the original issue and accepted answer."""
    articles = []
    hits = search_blog_posts(query, limit=max_articles * 4)
    rejected = 0
    for hit in hits:
        art = fetch_blog_article(hit["url"])
        if not art:
            continue
        if not art["title"]:
            art["title"] = hit["title"]
        if not is_relevant_blog_article(
            query=query,
            relevance_context=relevance_context,
            title=art["title"],
            text=art["text"],
        ):
            rejected += 1
            print(f"[한국어 블로그 제외] 주제/오류 불일치: {art['title'][:100]} ({art['url']})")
            continue
        articles.append(art)
        if len(articles) >= max_articles:
            break
    print(f"[한국어 블로그] 관련 자료 {len(articles)}건 채택, 관련성 부족 {rejected}건 제외")
    return articles
