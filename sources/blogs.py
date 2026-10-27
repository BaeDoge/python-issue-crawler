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
        net.note_error(url, "DuckDuckGo가 검색 결과를 주지 않음(봇 차단 또는 마크업 변경). "
                            "안정적으로 쓰려면 .env에 TAVILY_API_KEY(무료)를 설정하세요. "
                            f"응답 앞부분: {re.sub(r'\\s+', ' ', html[:120])!r}")
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


def blog_references(query: str, max_articles: int = 2) -> list:
    """검색 -> 본문 가져오기. 가져오기에 성공한 글만 최대 max_articles개 반환."""
    articles = []
    for hit in search_blog_posts(query, limit=max_articles * 3):
        art = fetch_blog_article(hit["url"])
        if art:
            if not art["title"]:
                art["title"] = hit["title"]
            articles.append(art)
        if len(articles) >= max_articles:
            break
    return articles
