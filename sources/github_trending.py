"""GitHub 인기/트렌딩 저장소 후보 수집기.

GITHUB_SSL_VERIFY=false가 기본값입니다. TLS 검증을 끈 경우 토큰은 전송하지 않습니다.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from requests.exceptions import RequestException

from config import OUTPUT_DIR

API_ROOT = "https://api.github.com"
DEFAULT_LIMIT = max(1, int(os.getenv("GITHUB_DISCOVERY_LIMIT", "8")))
SSL_VERIFY = os.getenv("GITHUB_SSL_VERIFY", "false").strip().lower() in {"1", "true", "yes"}
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "python-issue-crawler-opensource-discovery",
})
if SSL_VERIFY and TOKEN:
    SESSION.headers["Authorization"] = f"Bearer {TOKEN}"
elif not SSL_VERIFY and TOKEN:
    print("[보안 안내] GITHUB_SSL_VERIFY=false이므로 GITHUB_TOKEN은 요청에 포함하지 않습니다.")

SEARCH_GROUPS = [
    ("AI · 머신러닝", "topic:machine-learning stars:>100"),
    ("웹 · 프런트엔드", "topic:web-development stars:>100"),
    ("개발 도구", "topic:developer-tools stars:>100"),
    ("클라우드 · 인프라", "topic:devops stars:>100"),
    ("데이터베이스 · 데이터", "topic:database stars:>100"),
    ("보안", "topic:security stars:>100"),
    ("게임 · 그래픽", "topic:game-development stars:>100"),
    ("생산성 · 자동화", "topic:automation stars:>100"),
    ("기타 인기 프로젝트", "stars:>100"),
]


def _request(url: str, params: dict | None = None):
    response = SESSION.get(url, params=params, timeout=20, verify=SSL_VERIFY)
    response.raise_for_status()
    return response.json()


def _age_days(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except (TypeError, ValueError):
        return None


def _candidate(item: dict, group: str, kind: str) -> dict:
    stars = int(item.get("stargazers_count") or 0)
    forks = int(item.get("forks_count") or 0)
    age = _age_days(item.get("created_at"))
    pushed_days = _age_days(item.get("pushed_at"))
    license = (item.get("license") or {}).get("spdx_id") or "미확인"
    popularity = min(55.0, (stars ** 0.5) / 4)
    fork_signal = min(15.0, (forks ** 0.5) / 3)
    recency = 20.0 if pushed_days is not None and pushed_days <= 7 else (
        14.0 if pushed_days is not None and pushed_days <= 30 else
        7.0 if pushed_days is not None and pushed_days <= 90 else 0.0
    )
    score = round(min(100.0, popularity + fork_signal + recency + (10.0 if item.get("description") else 0.0)), 2)
    signals = [f"별 {stars:,}개",
               f"최근 업데이트 {pushed_days}일 전" if pushed_days is not None else "최근 업데이트 미확인"]
    if age is not None:
        signals.append(f"생성 {age}일 경과")
    return {
        "title": item.get("full_name") or item.get("name") or "Unknown repository",
        "link": item.get("html_url", ""),
        "source": "GitHub",
        "group": group,
        "kind": kind,
        "description": item.get("description") or "설명 없음",
        "stars": stars,
        "forks": forks,
        "open_issues": item.get("open_issues_count", 0),
        "created_at": item.get("created_at"),
        "pushed_at": item.get("pushed_at"),
        "age_days": age,
        "pushed_days": pushed_days,
        "default_branch": item.get("default_branch") or "main",
        "license": license,
        "language": item.get("language") or "미지정",
        "topics": item.get("topics") or [],
        "score": score,
        "signal": "; ".join(signals),
        "meta": f"group={group}; stars={stars}; forks={forks}; license={license}; score={score}",
    }


def discover_github_candidates(limit: int | None = None) -> dict:
    """전 분야의 인기 저장소와 최근 활동 저장소를 나눠 수집하고 JSON으로 저장합니다."""
    per_query = max(1, limit or DEFAULT_LIMIT)
    popular: dict[str, dict] = {}
    trending: dict[str, dict] = {}
    errors: list[str] = []
    since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

    # GitHub unauthenticated Search API는 검색 요청 제한이 낮으므로
    # 분야별 인기 검색 9회 + 전체 최근 활동 검색 1회로 10회 이내에 제한합니다.
    for group, base_query in SEARCH_GROUPS:
        print(f"[GitHub] {group} / 인기 검색 중...")
        try:
            payload = _request(
                f"{API_ROOT}/search/repositories",
                {"q": f"{base_query} archived:false", "per_page": min(100, per_query),
                 "sort": "stars", "order": "desc"},
            )
            for item in payload.get("items", []):
                full_name = item.get("full_name")
                if full_name and item.get("html_url"):
                    candidate = _candidate(item, group, "popular")
                    if full_name not in popular or candidate["score"] > popular[full_name]["score"]:
                        popular[full_name] = candidate
        except RequestException as exc:
            message = f"{group}/popular: {type(exc).__name__}: {exc}"
            errors.append(message)
            print(f"[경고] GitHub 검색 실패: {message}")
        except (ValueError, KeyError) as exc:
            errors.append(f"{group}/popular: {exc}")
            print(f"[경고] 응답 처리 실패: {group}: {exc}")
        time.sleep(0.3)

    # 최근 push가 있는 저장소를 분야 구분 없이 추가 검색하고 토픽으로 범주를 표시합니다.
    print("[GitHub] 전체 분야 / 최근 활동 검색 중...")
    try:
        payload = _request(
            f"{API_ROOT}/search/repositories",
            {"q": f"stars:>100 pushed:>{since} archived:false",
             "per_page": min(100, per_query), "sort": "updated", "order": "desc"},
        )
        for item in payload.get("items", []):
            full_name = item.get("full_name")
            if not full_name or not item.get("html_url"):
                continue
            topics = item.get("topics") or []
            group = next((label for label, marker in [
                ("AI · 머신러닝", "machine-learning"), ("웹 · 프런트엔드", "web"),
                ("개발 도구", "developer-tools"), ("클라우드 · 인프라", "devops"),
                ("데이터베이스 · 데이터", "database"), ("보안", "security"),
                ("게임 · 그래픽", "game-development"), ("생산성 · 자동화", "automation"),
            ] if marker in topics), "기타 인기 프로젝트")
            trending[full_name] = _candidate(item, group, "trending")
    except RequestException as exc:
        message = f"all/trending: {type(exc).__name__}: {exc}"
        errors.append(message)
        print(f"[경고] GitHub 최근 활동 검색 실패: {message}")
    except (ValueError, KeyError) as exc:
        errors.append(f"all/trending: {exc}")
        print(f"[경고] 최근 활동 응답 처리 실패: {exc}")

    popular_items = sorted(popular.values(), key=lambda x: (x["stars"], x["score"]), reverse=True)
    trending_items = sorted(
        trending.values(),
        key=lambda x: (x["pushed_days"] is not None and x["pushed_days"] <= 7, x["score"], x["stars"]),
        reverse=True,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"github_opensource_candidates_{datetime.now():%Y%m%d_%H%M%S}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": (
            "GitHub Search API 기반 휴리스틱 후보입니다. GitHub 전체 트렌딩 순위나 별점 증가량을 "
            "직접 측정한 결과가 아니며, 점수는 품질·보안·유지보수·라이선스 적합성을 보증하지 않습니다."
        ),
        "popular": popular_items,
        "trending": trending_items,
        "errors": errors,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON 저장: {output_path}")
    print(f"인기 후보 {len(popular_items)}개 / 최근 활동 후보 {len(trending_items)}개")
    if errors:
        print(f"검색 오류 {len(errors)}건. 네트워크/인증서 정책 또는 GitHub API 제한을 확인하세요.")
    return payload


def print_candidates(payload: dict, display_limit: int = 15) -> None:
    for key, heading in (("popular", "인기 프로젝트"), ("trending", "최근 활동 프로젝트")):
        print("\n" + "=" * 76 + "\n" + heading + "\n" + "=" * 76)
        items = payload.get(key, [])
        if not items:
            print("후보가 없습니다.")
            continue
        for index, item in enumerate(items[:display_limit], 1):
            print(f"{index:>2}. [{item['group']}] {item['title']}")
            print(f"    ⭐ {item['stars']:,} | Fork {item['forks']:,} | 점수 {item['score']}/100")
            print(f"    언어: {item['language']} | 라이선스: {item['license']}")
            print(f"    {item['description']}\n    {item['link']}")
    print("\n참고: 최근 활동은 별점 증가량과 같지 않습니다. 선택 전 저장소와 라이선스를 확인하세요.")


def fetch_repository_context(candidate: dict) -> dict:
    """선택한 저장소의 메타데이터와 README를 가져옵니다."""
    full_name = candidate.get("title", "")
    if not full_name or "/" not in full_name or " " in full_name:
        return {}
    try:
        repo = _request(f"{API_ROOT}/repos/{quote(full_name, safe='/')}")
    except RequestException as exc:
        print(f"[GitHub] 저장소 상세 정보 수집 실패: {exc}")
        return {}
    branch = repo.get("default_branch") or "main"
    tree_paths: list[str] = []
    file_texts: list[tuple[str, str]] = []
    try:
        tree_payload = _request(
            f"{API_ROOT}/repos/{quote(full_name, safe='/')}/git/trees/{quote(branch, safe='')}?recursive=1"
        )
        tree_paths = [
            entry.get("path", "") for entry in tree_payload.get("tree", [])
            if entry.get("type") == "blob" and entry.get("path")
        ][:2500]
    except (RequestException, ValueError) as exc:
        print(f"[GitHub] 파일 트리 조회 실패(메타데이터로 계속 진행): {exc}")

    # README만 요약하지 않도록 아키텍처 문서, 보안 문서, 의존성 선언, 구현 파일을 함께 수집합니다.
    preferred_exact = [
        "README.md", "README.rst", "README", "SECURITY.md", "CONTRIBUTING.md",
        "ARCHITECTURE.md", "docs/architecture.md", "package.json", "pyproject.toml",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Dockerfile",
        "LICENSE", "LICENSE.md", "AGENTS.md",
    ]
    selected_paths = [p for p in preferred_exact if p in tree_paths]
    source_candidates = [
        p for p in tree_paths
        if any(token in p.lower() for token in (
            "mcp", "server", "agent", "analy", "reverse", "decompil", "security",
            "architecture", "plugin", "tool", "parser", "entry"
        ))
        and p.lower().endswith((".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".md", ".mdx"))
        and not any(part in p.lower() for part in ("node_modules/", "vendor/", "dist/", "build/", "lock"))
    ]
    for path in source_candidates:
        if path not in selected_paths:
            selected_paths.append(path)
    selected_paths = selected_paths[:9]

    for path in selected_paths:
        url = f"https://raw.githubusercontent.com/{full_name}/{quote(branch, safe='')}/{quote(path, safe='/')}"
        try:
            response = SESSION.get(url, timeout=20, verify=SSL_VERIFY)
            if response.status_code == 200 and len(response.text) < 180_000:
                file_texts.append((path, response.text[:7000]))
        except RequestException:
            continue

    license_info = repo.get("license") or {}
    parts = [
        f"프로젝트: {repo.get('full_name', full_name)}",
        f"URL: {repo.get('html_url', candidate.get('link', ''))}",
        f"설명: {repo.get('description') or '설명 없음'}",
        f"주요 언어: {repo.get('language') or '미지정'}",
        f"Stars: {repo.get('stargazers_count', 0)} / Forks: {repo.get('forks_count', 0)}",
        f"생성일: {repo.get('created_at', '미확인')} / 최근 push: {repo.get('pushed_at', '미확인')}",
        f"라이선스 SPDX: {license_info.get('spdx_id') or '미확인'}",
        f"저장소 토픽: {', '.join(repo.get('topics') or []) or '없음'}",
        f"보관(archived) 여부: {repo.get('archived', False)}",
        f"기본 브랜치: {branch}",
        "",
        "저장소 파일 경로(일부):",
        "\n".join(f"- {p}" for p in tree_paths[:180]) or "파일 트리를 가져오지 못했습니다.",
        "",
        "추가로 수집한 공식 저장소 파일(원문 자료, 그대로 복사하지 말 것):",
    ]
    for path, text_content in file_texts:
        parts.extend(["", f"--- FILE: {path} ---", text_content])
    return {
        "context_text": "\n".join(parts),
        "source_url": repo.get("html_url", candidate.get("link")),
        "sources": [{
            "platform": "GitHub", "title": repo.get("full_name", full_name),
            "url": repo.get("html_url", candidate.get("link")),
            "author": (repo.get("owner") or {}).get("login"),
        }] + [
            {"platform": "GitHub", "title": f"{repo.get('full_name', full_name)} / {path}",
             "url": f"https://github.com/{full_name}/blob/{branch}/{path}",
             "author": (repo.get("owner") or {}).get("login")}
            for path, _ in file_texts if path not in ("README.md", "README.rst", "README")
        ],
        "third_party": False,
        "repository": repo,
    }

