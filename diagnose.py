"""
연결 진단 — `uv run pipeline/engine.py --diagnose`
========================================================================
후보 수집이 "하나도 못 찾았습니다"로 끝날 때, 소스별로 실제 접속이 되는지 하나씩 시험해서
성공/실패와 정확한 실패 원인을 보여줍니다. 실패하면 마지막에 나오는 "수집된 오류"
블록을 그대로 복사해서 알려주시면 원인을 바로 짚을 수 있습니다.
"""

import os
import platform
import ssl
import sys
import urllib.request

import config
from sources import net, web, algorithm, blogs

_HINTS = [
    (("CERTIFICATE_VERIFY_FAILED", "SSLError"),
     "HTTPS 인증서 검증 실패 — 회사/보안 프로그램이 HTTPS를 가로채는 환경일 수 있습니다. "
     "`uv add truststore` 후 다시 실행(Windows 인증서 저장소를 사용함), 또는 사내 루트 인증서 파일 경로를 "
     ".env의 REQUESTS_CA_BUNDLE에 지정하세요."),
    (("ProxyError",),
     "프록시 접속 실패 — .env에 HTTPS_PROXY=http://주소:포트 를 지정해보세요."),
    (("ConnectTimeout", "ReadTimeout", "ConnectionError", "NameResolution", "getaddrinfo", "Max retries"),
     "접속 자체가 안 됩니다 — 방화벽/DNS/프록시로 막혔을 가능성이 큽니다(브라우저로는 열리는지 확인)."),
    (("HTTP 403",),
     "접근 거부 — 요청 한도 초과나 봇 차단입니다. GitHub면 .env에 GITHUB_TOKEN(무료, 권한 체크 없이 발급)을 "
     "설정하세요. LeetCode면 Cloudflare 차단일 수 있어서 이 오류 문구를 그대로 알려주세요."),
    (("HTTP 429",), "요청 한도 초과 — 잠시 후 다시 시도하거나 토큰/키를 설정하세요."),
    (("GraphQL 오류",), "LeetCode 쿼리가 거부됐습니다(스키마 변경 가능성) — 이 오류 문구를 그대로 알려주세요."),
]


def _show(ok: bool, name: str, detail: str) -> bool:
    print(f"{'✅' if ok else '❌'} {name}: {detail}")
    return ok


def _safe(name: str, fn) -> bool:
    try:
        ok, detail = fn()
        return _show(ok, name, detail)
    except Exception as e:  # 진단 자체가 죽으면 안 됨
        return _show(False, name, f"예외 {type(e).__name__}: {str(e)[:200]}")


def run_diagnose() -> None:
    print("=" * 60)
    print("연결 진단")
    print("=" * 60)
    print(f"Python {sys.version.split()[0]} / {platform.platform()} / {ssl.OPENSSL_VERSION}")
    print(f"시스템 프록시 설정: {urllib.request.getproxies() or '없음'}")
    print(f"시스템 인증서 사용(truststore): {'켜짐' if config.SYSTEM_CERTS_ACTIVE else '꺼짐/미설치'}")
    print(f"GITHUB_TOKEN: {'있음' if os.getenv('GITHUB_TOKEN') else '없음'} / "
          f"TAVILY_API_KEY: {'있음' if os.getenv('TAVILY_API_KEY') else '없음'}")
    print("-" * 60)

    net.LAST_ERRORS.clear()

    def basic():
        text = net.get_text("https://example.com", timeout=10)
        return bool(text), f"{len(text)}자 수신" if text else "응답 없음"

    def github():
        data = net.get_json("https://api.github.com/rate_limit", headers=web._github_headers(), timeout=10)
        if not data:
            return False, "응답 없음"
        s = data["resources"]["search"]; c = data["resources"]["core"]
        return True, f"search 남은 한도 {s['remaining']}/{s['limit']}, core {c['remaining']}/{c['limit']}"

    def so_info():
        data = net.get_json("https://api.stackexchange.com/2.3/info?site=stackoverflow", timeout=10)
        if not data:
            return False, "응답 없음"
        return True, f"gzip 응답 정상 해석, 오늘 남은 요청 {data.get('quota_remaining')}/{data.get('quota_max')}"

    def so_seed():
        items = web.stackoverflow_for_seed("ModuleNotFoundError: No module named", limit=3)
        return bool(items), (f"{len(items)}건, 예: {items[0]['title'][:50]}" if items else "0건(필터에 맞는 결과가 없거나 요청 실패)")

    def lc_content():
        p = algorithm.fetch_leetcode_problem("two-sum")
        return bool(p["description"]), (f"'{p['title']}' 지문 {len(p['description'])}자" if p["description"] else "지문을 못 가져옴")

    def lc_list():
        cands = algorithm.leetcode_candidates(limit=3)
        if cands and cands[0]["source"] == "leetcode":
            return True, f"{len(cands)}건 (목록 조회 정상)"
        return False, "목록 조회 실패 → 폴백 문제 풀 사용 중(지문 조회만 되면 글 생성은 가능)"

    articles = {}

    def blog_search():
        hits = blogs.search_blog_posts("파이썬 ModuleNotFoundError 해결", limit=3)
        articles["hits"] = hits
        return bool(hits), (f"{len(hits)}건, 예: {hits[0]['url']}" if hits else "0건(검색 실패 — TAVILY_API_KEY 설정을 권장)")

    def blog_fetch():
        for h in articles.get("hits", []):
            art = blogs.fetch_blog_article(h["url"])
            if art:
                return True, f"{art['platform']} 본문 {len(art['text'])}자, 이미지 후보 {len(art['image_urls'])}개"
        return False, "본문 추출 실패(검색 결과가 없거나 페이지 구조/접근 문제)"

    results = {}
    for name, fn in [("기본 인터넷(example.com)", basic), ("GitHub API", github),
                     ("StackOverflow API", so_info), ("StackOverflow 시드 검색", so_seed),
                     ("LeetCode 지문", lc_content), ("LeetCode 목록", lc_list),
                     ("블로그 검색", blog_search), ("블로그 본문", blog_fetch)]:
        results[name] = _safe(name, fn)

    print("-" * 60)
    if net.LAST_ERRORS:
        print("수집된 오류 (실패가 있으면 이 블록을 그대로 복사해서 알려주세요):")
        seen = set()
        for line in net.LAST_ERRORS:
            if line not in seen:
                seen.add(line)
                print("  " + line)
        print()
        shown = set()
        for needles, hint in _HINTS:
            if any(n in line for line in seen for n in needles) and hint not in shown:
                shown.add(hint)
                print(f"💡 {hint}")
    ok_count = sum(results.values())
    print(f"\n결과: {ok_count}/{len(results)} 통과")
    if not results["StackOverflow 시드 검색"]:
        print("→ 트러블슈팅은 StackOverflow가 핵심 소스라서 이 항목이 통과해야 합니다.")
    if not (results["LeetCode 지문"]):
        print("→ 알고리즘은 'LeetCode 지문'이 통과해야 글을 만들 수 있습니다.")
