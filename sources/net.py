"""
공용 HTTP 계층 — 모든 소스 모듈이 이걸 통해 네트워크에 접근합니다.
========================================================================
이전 버전의 문제 두 가지를 고치기 위한 모듈입니다.

1. gzip 응답을 못 풀었음: StackExchange API는 요청 헤더와 무관하게 항상 gzip으로
   응답하는데, 표준 urllib은 자동으로 풀어주지 않아서 JSON 파싱이 실패했습니다.
   requests는 Content-Encoding을 보고 자동으로 풉니다.
2. 실패 원인이 안 보였음: 예외를 전부 삼키고 빈 리스트를 돌려줘서, "후보가 없다"는
   결과만 보이고 왜 실패했는지(SSL, 프록시, 차단, 요청 한도 ...) 알 수 없었습니다.
   이제 실패하면 원인을 한 번씩 화면에 출력하고, `engine.py --diagnose`가 같은 정보를
   모아서 보여줍니다.

호출부는 실패 시 None(또는 빈 값)을 받고 파이프라인은 계속 진행합니다 — 달라진 건
"조용히"가 아니라 "이유를 말하고" 실패한다는 점입니다.
"""

import re
from urllib.parse import urlparse

import requests

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_REPORTED: set = set()
LAST_ERRORS: list = []


def _report(url: str, detail: str, quiet: bool = False, record: bool = True) -> None:
    host = urlparse(url).netloc
    msg = f"[네트워크 오류] {host}: {detail}"
    if record:
        LAST_ERRORS.append(msg)
    key = (host, detail[:60])
    if not quiet and key not in _REPORTED:
        _REPORTED.add(key)
        print(msg)


def note_error(url: str, detail: str) -> None:
    """요청은 성공했지만 쓸 수 있는 내용이 아니었던 경우(예: 검색엔진의 봇 차단 페이지) 기록."""
    _report(url, detail)


def request(method: str, url: str, *, headers: dict | None = None, json_body=None,
            timeout: int = 15, session=None, quiet: bool = False, record: bool = True):
    """성공(2xx/3xx)이면 Response, 실패면 원인을 기록/출력하고 None."""
    h = {"User-Agent": BROWSER_UA}
    if headers:
        h.update(headers)
    try:
        r = (session or requests).request(method, url, headers=h, json=json_body, timeout=timeout)
    except requests.RequestException as e:
        _report(url, f"{type(e).__name__}: {str(e)[:220]}", quiet, record)
        return None
    if r.status_code >= 400:
        snippet = re.sub(r"\s+", " ", r.text[:160])
        _report(url, f"HTTP {r.status_code} {r.reason} — {snippet}", quiet, record)
        return None
    return r


def _json_of(r, url: str):
    if r is None:
        return None
    try:
        return r.json()
    except ValueError:
        _report(url, f"JSON이 아닌 응답: {r.text[:120]!r}")
        return None


def get_json(url: str, **kw):
    return _json_of(request("GET", url, **kw), url)


def post_json(url: str, payload: dict, **kw):
    return _json_of(request("POST", url, json_body=payload, **kw), url)


def get_text(url: str, **kw):
    r = request("GET", url, **kw)
    if r is None:
        return None
    # Content-Type에 charset이 없으면 requests는 ISO-8859-1로 가정해서 한글이 깨진다 -> 내용으로 추정
    if "charset" not in r.headers.get("Content-Type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def get_bytes(url: str, **kw):
    r = request("GET", url, **kw)
    return r.content if r is not None else None
