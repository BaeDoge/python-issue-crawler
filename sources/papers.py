"""Academic-paper discovery and source-context collection (OpenAlex + arXiv)."""
from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from sources import net

OPENALEX_API = "https://api.openalex.org/works"
SEARCH_TERMS = [
    "large language models", "retrieval augmented generation", "AI agents",
    "multimodal learning", "computer vision", "natural language processing",
    "machine learning systems", "software engineering AI", "database systems",
    "robotics", "information retrieval", "speech recognition",
    "인공지능", "대규모 언어 모델", "검색 증강 생성", "멀티모달",
    "컴퓨터 비전", "자연어 처리", "소프트웨어 공학", "데이터베이스",
]
MAX_PAPERS = 80
MIN_ABSTRACT_CHARS = 180


def _abstract_from_index(index: dict | None) -> str:
    if not isinstance(index, dict):
        return ""
    words = []
    for token, positions in index.items():
        if isinstance(positions, list):
            words.extend((pos, token) for pos in positions if isinstance(pos, int) and pos >= 0)
    return " ".join(token for _, token in sorted(words))


def _authors(work: dict) -> list[str]:
    return [
        author["author"]["display_name"]
        for author in (work.get("authorships") or [])
        if (author.get("author") or {}).get("display_name")
    ][:12]


def _is_korean_affiliated(work: dict) -> bool:
    return any(
        (institution.get("country_code") or "").upper() == "KR"
        for authorship in (work.get("authorships") or [])
        for institution in (authorship.get("institutions") or [])
    )


def _candidate(work: dict, query: str) -> dict | None:
    title = (work.get("title") or "").strip()
    abstract = _abstract_from_index(work.get("abstract_inverted_index"))
    doi = work.get("doi")
    paper_id = work.get("id", "")
    landing = ((work.get("best_oa_location") or {}).get("landing_page_url") or doi or paper_id)
    if not title or not landing or len(abstract) < MIN_ABSTRACT_CHARS:
        return None
    is_domestic = _is_korean_affiliated(work)
    return {
        "title": title, "link": landing, "source": "OpenAlex",
        "paper_id": paper_id, "doi": doi,
        "publication_date": work.get("publication_date") or "",
        "year": work.get("publication_year"), "authors": _authors(work),
        "venue": ((work.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "is_domestic": is_domestic, "query": query, "abstract": abstract,
        "pdf_url": (work.get("best_oa_location") or {}).get("pdf_url"),
        "type": "domestic" if is_domestic else "international",
        "signal": f"{'국내 소속' if is_domestic else '국내 기관 소속 미확인'} · {work.get('publication_year') or '연도 미확인'} · 인용 {int(work.get('cited_by_count') or 0)}회",
        "meta": f"분류={'국내 연구' if is_domestic else '국내 기관 소속 미확인'}; 발행={work.get('publication_date') or '미확인'}; DOI={doi or '없음'}",
    }


def discover_candidates() -> list[dict]:
    """Collect domestic-affiliated and international research, deduplicated by DOI/URL."""
    collected: dict[str, dict] = {}
    # Balance a bounded search batch across English and Korean queries.
    selected_terms = SEARCH_TERMS[:6] + SEARCH_TERMS[12:18]
    for index, term in enumerate(selected_terms):
        params = {
            "search": term,
            "filter": "type:article|preprint|proceedings-article,is_retracted:false,from_publication_date:2019-01-01",
            "per-page": 20,
            "sort": "publication_date:desc",
        }
        data = net.get_json(OPENALEX_API, params=params, timeout=25)
        if not isinstance(data, dict):
            print(f"[논문] OpenAlex 검색 실패: {term}")
            continue
        for work in data.get("results", []):
            item = _candidate(work, term)
            if not item:
                continue
            key = (item.get("doi") or item["link"]).casefold()
            previous = collected.get(key)
            if previous is None or item["cited_by_count"] > previous["cited_by_count"]:
                collected[key] = item
        if index and index % 4 == 0:
            time.sleep(0.15)

    candidates = list(collected.values())
    candidates.sort(key=lambda p: (p.get("publication_date") or "", p.get("cited_by_count", 0)), reverse=True)
    domestic = sum(1 for item in candidates if item["is_domestic"])
    print(f"[논문 후보] OpenAlex {len(candidates)}편 (국내 소속 연구 {domestic}, 해외/국제 연구 {len(candidates)-domestic})")
    return candidates


def _arxiv_html_url(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+(?:v[0-9]+)?)", url or "")
    return f"https://arxiv.org/html/{match.group(1)}" if match else None


def _extract_code_links(text: str) -> list[str]:
    """Only retain GitHub links explicitly labelled as code/implementation resources."""
    soup = BeautifulSoup(text or "", "html.parser")
    unique, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        url = anchor.get("href", "").strip()
        if not re.match(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", url, re.I):
            continue
        surrounding = anchor.get_text(" ", strip=True)
        if anchor.parent:
            surrounding += " " + anchor.parent.get_text(" ", strip=True)[:300]
        if not re.search(r"\b(code|implementation|github|repository|source code)\b", surrounding, re.I):
            continue
        clean = url.rstrip(".,);]")
        if clean.casefold() not in seen:
            seen.add(clean.casefold())
            unique.append(clean)
    return unique[:12]

def build_context(chosen: dict) -> dict:
    abstract = (chosen.get("abstract") or "").strip()
    landing = chosen.get("link") or ""
    if len(abstract) < MIN_ABSTRACT_CHARS or not landing:
        return {}
    parts = [
        f"논문 제목: {chosen['title']}", f"논문 원문/랜딩 페이지: {landing}",
        f"DOI: {chosen.get('doi') or '없음'}",
        f"발행일: {chosen.get('publication_date') or '확인되지 않음'}",
        f"저자: {', '.join(chosen.get('authors') or []) or '확인되지 않음'}",
        f"학술지/학회: {chosen.get('venue') or '확인되지 않음'}",
        f"인용 수(OpenAlex 조회 시점): {chosen.get('cited_by_count', 0)}",
        f"국내 연구 분류: {'저자 소속에 대한민국 기관 포함' if chosen.get('is_domestic') else '대한민국 기관 소속 확인 안 됨'}",
        "", "초록(원문):", abstract,
    ]
    evidence = [abstract]
    sources = [{"platform": "OpenAlex / 논문 원문", "title": chosen["title"], "url": landing,
                "author": ", ".join(chosen.get("authors") or []) or None}]
    if chosen.get("pdf_url"):
        parts.extend(["", f"공개 PDF: {chosen['pdf_url']}"])
        sources.append({"platform": "Open Access PDF", "title": "논문 PDF", "url": chosen["pdf_url"], "author": None})

    arxiv_html_url = _arxiv_html_url(landing)
    html_url = arxiv_html_url or (landing if landing.startswith("https://") and "doi.org/" not in landing else None)
    if html_url:
        html_text = net.get_text(html_url, timeout=25)
        if html_text:
            full_text = BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)
            if arxiv_html_url and len(full_text) > 1000:
                parts.extend(["", "arXiv HTML 원문 발췌:", full_text[:14000]])
                evidence.append(full_text[:14000])
                sources.append({"platform": "arXiv HTML 원문", "title": chosen["title"], "url": html_url, "author": None})
            code_links = _extract_code_links(html_text)
            if code_links:
                parts.extend(["", "논문 페이지에서 확인한 GitHub 코드 링크:"] + [f"- {url}" for url in code_links])
                sources.extend({"platform": "논문 연결 코드", "title": url.rsplit("/", 1)[-1], "url": url, "author": None} for url in code_links)
            else:
                parts.extend(["", "공식 코드 링크: 논문 페이지에서 확인되지 않음. URL을 만들어내지 말 것."])
    else:
        parts.extend(["", "공식 코드 링크: 확인 가능한 원문 HTML에서 찾지 못함. 코드가 공개되어 있다고 추정하지 말 것."])

    parts.extend([
        "", "분석 시 주의:",
        "- 초록만 확보된 경우 논문 전체의 실험 설정, 수치, 한계가 확인된 것처럼 작성하지 말 것.",
        "- 초록의 주장을 한국어로 번역하되, 저자 주장과 작성자의 해석을 구분할 것.",
        "- 코드 링크가 확인되지 않으면 공식 구현 공개 여부를 확인할 수 없다고 명시할 것.",
    ])
    return {
        "context_text": "\n".join(parts), "review_context": "\n".join(evidence),
        "source_url": landing, "sources": sources, "images": [], "third_party": False,
        "analysis_source_count": len(evidence),
    }
