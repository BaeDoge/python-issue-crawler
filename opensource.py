
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output_files"
GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co/api"

TIMEOUT = 20
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "python-issue-crawler-opensource-discovery/1.0",
    "Accept": "application/vnd.github+json",
})

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
if GITHUB_TOKEN:
    SESSION.headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"


# 검색 범위는 AI/ML과 Python 개발 도구로 한정한다.
GITHUB_QUERIES = [
    {
        "name": "AI/ML",
        "query": "language:Python topic:machine-learning",
    },
    {
        "name": "LLM tools",
        "query": "language:Python (LLM OR RAG OR inference)",
    },
    {
        "name": "Python developer tools",
        "query": "language:Python topic:developer-tools",
    },
]

HF_QUERIES = [
    {"name": "text-to-image", "query": "text-to-image"},
    {"name": "text-to-video", "query": "text-to-video"},
    {"name": "text-to-speech", "query": "text-to-speech"},
    {"name": "embedding", "query": "embedding"},
    {"name": "LLM", "query": "LLM"},
]

NOW = datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    """ISO 날짜 문자열을 UTC datetime으로 변환한다."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 2)


def request_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """HTTP 요청을 수행한다. 실패한 검색 하나 때문에 전체 실행이 중단되지 않게 한다."""
    try:
        response = SESSION.get(url, params=params, timeout=TIMEOUT)

        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset = response.headers.get("X-RateLimit-Reset")
            print(
                f"[경고] 접근 제한: {response.url} "
                f"(remaining={remaining}, reset={reset})",
                file=sys.stderr,
            )
            return None

        response.raise_for_status()
        return response.json()

    except requests.RequestException as exc:
        print(f"[경고] 요청 실패: {url} - {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"[경고] JSON 응답 해석 실패: {url} - {exc}", file=sys.stderr)

    return None


def license_name(repository: dict[str, Any]) -> str | None:
    license_info = repository.get("license") or {}
    return license_info.get("spdx_id") or license_info.get("name")


def github_recency_score(pushed_at: str | None) -> tuple[float, int | None]:
    pushed = parse_datetime(pushed_at)
    if not pushed:
        return 0, None

    days = max(0, (NOW - pushed).days)

    if days <= 30:
        score = 25
    elif days <= 90:
        score = 21
    elif days <= 180:
        score = 16
    elif days <= 365:
        score = 10
    elif days <= 730:
        score = 5
    else:
        score = 0

    return score, days


def github_candidate(
    repo: dict[str, Any],
    discovery_type: str,
    query_name: str,
) -> dict[str, Any]:
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    description = (repo.get("description") or "").strip()
    license_value = license_name(repo)
    topics = repo.get("topics") or []
    recency, days_since_push = github_recency_score(repo.get("pushed_at"))

    # 누적 관심도. 별점이 아주 큰 프로젝트가 모든 항목을 압도하지 않도록 로그를 쓴다.
    popularity = min(25, math.log10(stars + 1) / 4 * 25)
    fork_signal = min(8, math.log10(forks + 1) / 3 * 8)
    description_signal = 5 if description else 0
    license_signal = 7 if license_value and license_value.lower() != "other" else 0
    topic_signal = min(5, len(topics))

    created = parse_datetime(repo.get("created_at"))
    age_days = max(0, (NOW - created).days) if created else None

    if discovery_type == "established":
        score = (
            popularity
            + fork_signal
            + recency
            + description_signal
            + license_signal
            + topic_signal
        )
        reasons = [
            f"GitHub stars: {stars:,}",
            f"forks: {forks:,}",
            f"최근 push: {days_since_push}일 전"
            if days_since_push is not None else "최근 push 날짜 미확인",
        ]
    else:
        # 신규성 점수는 저장소 생성일이 있을 때만 반영한다.
        # 최근 업데이트만으로 새 프로젝트라고 단정하지 않는다.
        if age_days is None:
            freshness = 0
        elif age_days <= 180:
            freshness = 25
        elif age_days <= 365:
            freshness = 20
        elif age_days <= 730:
            freshness = 12
        elif age_days <= 1095:
            freshness = 5
        else:
            freshness = 0

        moderate_interest = min(15, math.log10(stars + 1) / 3 * 15)
        score = (
            freshness
            + moderate_interest
            + recency
            + description_signal
            + license_signal
            + min(5, len(topics))
        )
        reasons = [
            f"저장소 생성 후 {age_days}일"
            if age_days is not None else "생성일 미확인",
            f"GitHub stars: {stars:,}",
            f"최근 push: {days_since_push}일 전"
            if days_since_push is not None else "최근 push 날짜 미확인",
        ]

    if not license_value:
        reasons.append("라이선스 미확인: 사용 조건 확인 필요")

    return {
        "platform": "github",
        "project_type": "python_repository",
        "discovery_type": discovery_type,
        "query_group": query_name,
        "name": repo.get("full_name") or repo.get("name") or "",
        "title": repo.get("full_name") or repo.get("name") or "",
        "description": description,
        "url": repo.get("html_url"),
        "homepage": repo.get("homepage"),
        "language": repo.get("language"),
        "license": license_value,
        "created_at": repo.get("created_at"),
        "last_updated_at": repo.get("pushed_at"),
        "days_since_last_push": days_since_push,
        "age_days": age_days,
        "stars": stars,
        "forks": forks,
        "open_issues": repo.get("open_issues_count"),
        "topics": topics,
        "score": clamp(score),
        "score_reasons": reasons,
        "score_note": (
            "메타데이터 기반 탐색 점수이며, 프로젝트 품질이나 성장률을 "
            "직접 측정한 값은 아님."
        ),
    }


def search_github(
    query: str,
    query_name: str,
    limit: int,
    discovery_type: str,
) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "per_page": min(max(limit, 1), 100),
        "sort": "stars" if discovery_type == "established" else "updated",
        "order": "desc",
    }

    data = request_json(f"{GITHUB_API}/search/repositories", params=params)
    if not isinstance(data, dict):
        return []

    results = []
    for repo in data.get("items", []):
        if not isinstance(repo, dict):
            continue

        # 보관처리된 저장소는 신규 후보에서 제외한다.
        if repo.get("archived"):
            continue

        results.append(
            github_candidate(repo, discovery_type, query_name)
        )

    return results


def hf_recency_score(last_modified: str | None) -> tuple[float, int | None]:
    modified = parse_datetime(last_modified)
    if not modified:
        return 0, None

    days = max(0, (NOW - modified).days)

    if days <= 30:
        score = 25
    elif days <= 90:
        score = 20
    elif days <= 180:
        score = 15
    elif days <= 365:
        score = 8
    else:
        score = 0

    return score, days


def hf_license(tags: list[str]) -> str | None:
    for tag in tags:
        if tag.startswith("license:"):
            return tag.partition(":")[2]
    return None


def hf_candidate(
    model: dict[str, Any],
    discovery_type: str,
    query_name: str,
) -> dict[str, Any]:
    downloads = int(model.get("downloads") or 0)
    likes = int(model.get("likes") or 0)
    tags = model.get("tags") or []
    last_modified = model.get("lastModified")
    recency, days_since_update = hf_recency_score(last_modified)
    license_value = hf_license(tags)

    popularity = min(25, math.log10(downloads + 1) / 6 * 25)
    likes_signal = min(10, math.log10(likes + 1) / 3 * 10)
    license_signal = 7 if license_value else 0
    task_signal = 5 if model.get("pipeline_tag") else 0
    library_signal = 3 if model.get("library_name") else 0

    if discovery_type == "established":
        score = (
            popularity
            + likes_signal
            + recency
            + license_signal
            + task_signal
            + library_signal
        )
        reasons = [
            f"다운로드 수: {downloads:,}",
            f"좋아요: {likes:,}",
            f"최근 업데이트: {days_since_update}일 전"
            if days_since_update is not None else "최근 업데이트 날짜 미확인",
        ]
    else:
        # Hub API 응답의 생성일이 보장되지 않으므로 신규 프로젝트 여부를
        # 생성일 기준으로 단정하지 않는다. 여기서는 관심 규모와 업데이트 신호를 쓴다.
        lower_popularity = max(0, 15 - popularity * 0.45)
        score = (
            lower_popularity
            + likes_signal
            + recency
            + license_signal
            + task_signal
            + library_signal
        )
        reasons = [
            f"다운로드 수: {downloads:,}",
            f"좋아요: {likes:,}",
            f"최근 업데이트: {days_since_update}일 전"
            if days_since_update is not None else "최근 업데이트 날짜 미확인",
            "신흥 후보 휴리스틱: 생성일 또는 실제 성장률을 의미하지 않음",
        ]

    if not license_value:
        reasons.append("라이선스 태그 미확인: 모델 카드에서 사용 조건 확인 필요")

    model_id = model.get("id") or model.get("modelId") or ""
    return {
        "platform": "huggingface",
        "project_type": "model",
        "discovery_type": discovery_type,
        "query_group": query_name,
        "name": model_id,
        "title": model_id,
        "description": "",
        "url": f"https://huggingface.co/{model_id}" if model_id else None,
        "homepage": None,
        "language": None,
        "license": license_value,
        "created_at": None,
        "last_updated_at": last_modified,
        "days_since_last_push": days_since_update,
        "age_days": None,
        "downloads": downloads,
        "likes": likes,
        "pipeline_tag": model.get("pipeline_tag"),
        "library_name": model.get("library_name"),
        "tags": tags[:30],
        "score": clamp(score),
        "score_reasons": reasons,
        "score_note": (
            "Hugging Face 메타데이터 기반 탐색 점수. "
            "GitHub 저장소 점수와 직접 비교할 수 없음."
        ),
    }


def search_huggingface(
    query: str,
    query_name: str,
    limit: int,
    discovery_type: str,
) -> list[dict[str, Any]]:
    # Hub API의 정렬 필드는 모델의 다운로드 수 또는 최근 수정일이다.
    params = {
        "search": query,
        "limit": min(max(limit, 1), 100),
        "sort": "downloads" if discovery_type == "established" else "lastModified",
        "direction": "-1",
        "full": "false",
    }

    data = request_json(f"{HF_API}/models", params=params)
    if not isinstance(data, list):
        return []

    results = []
    for model in data:
        if not isinstance(model, dict):
            continue
        results.append(hf_candidate(model, discovery_type, query_name))

    return results


def deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """검색어가 달라 중복 수집된 동일 프로젝트를 URL 기준으로 제거한다."""
    unique: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        key = candidate.get("url") or candidate.get("name")
        if not key:
            continue

        previous = unique.get(key)
        if previous is None or candidate["score"] > previous["score"]:
            unique[key] = candidate

    return list(unique.values())


def collect_candidates(
    source: str,
    per_query: int,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "established": [],
        "emerging": [],
    }

    for discovery_type in ("established", "emerging"):
        if source in ("both", "github"):
            for item in GITHUB_QUERIES:
                print(
                    f"[GitHub] {discovery_type} / {item['name']} 검색 중..."
                )
                groups[discovery_type].extend(
                    search_github(
                        query=item["query"],
                        query_name=item["name"],
                        limit=per_query,
                        discovery_type=discovery_type,
                    )
                )

        if source in ("both", "huggingface"):
            for item in HF_QUERIES:
                print(
                    f"[Hugging Face] {discovery_type} / {item['name']} 검색 중..."
                )
                groups[discovery_type].extend(
                    search_huggingface(
                        query=item["query"],
                        query_name=item["name"],
                        limit=per_query,
                        discovery_type=discovery_type,
                    )
                )

        groups[discovery_type] = sorted(
            deduplicate(groups[discovery_type]),
            key=lambda item: item["score"],
            reverse=True,
        )

    return groups


def print_group(
    title: str,
    candidates: list[dict[str, Any]],
    limit: int,
) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")

    if not candidates:
        print("후보가 없습니다. 네트워크 또는 API 제한을 확인하세요.")
        return

    for index, item in enumerate(candidates[:limit], start=1):
        print(f"\n{index}. [{item['platform']}] {item['title']}")
        print(f"   점수: {item['score']}/100")
        print(f"   URL: {item.get('url') or '(없음)'}")

        description = (item.get("description") or "").strip()
        if description:
            print(f"   설명: {description[:220]}")

        if item["platform"] == "github":
            print(
                f"   stars={item.get('stars', 0):,}, "
                f"forks={item.get('forks', 0):,}, "
                f"license={item.get('license') or '미확인'}"
            )
        else:
            print(
                f"   downloads={item.get('downloads', 0):,}, "
                f"likes={item.get('likes', 0):,}, "
                f"license={item.get('license') or '미확인'}"
            )

        print(f"   선정 신호: {'; '.join(item.get('score_reasons', []))}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GitHub와 Hugging Face에서 오픈소스 분석 후보를 수집합니다."
    )
    parser.add_argument(
        "--source",
        choices=("both", "github", "huggingface"),
        default="both",
        help="검색 대상 (기본값: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="검색어별 후보 수 (기본값: 5, 최대 100)",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=10,
        help="유형별 화면 출력 수 (기본값: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON 출력 경로 (기본값: output_files에 자동 생성)",
    )
    args = parser.parse_args()

    if args.limit < 1 or args.show < 1:
        parser.error("--limit과 --show는 1 이상이어야 합니다.")

    print("오픈소스 후보 수집 시작")
    print(f"검색 대상: {args.source}")
    print(f"검색어별 후보 수: {args.limit}")

    groups = collect_candidates(args.source, args.limit)

    print_group("검증된 프로젝트 후보", groups["established"], args.show)
    print_group("신흥/최근 활동 후보", groups["emerging"], args.show)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or (
        OUTPUT_DIR
        / f"opensource_candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "score_warning": (
            "점수는 후보 탐색용 휴리스틱이다. 프로젝트 품질, 성장률, "
            "보안성 또는 라이선스 적합성을 보증하지 않는다. "
            "GitHub와 Hugging Face의 점수는 직접 비교하지 않는다."
        ),
        "established": groups["established"],
        "emerging": groups["emerging"],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nJSON 저장 완료: {output_path.resolve()}")
    print(
        f"후보 수: 검증된 {len(groups['established'])}개 / "
        f"신흥 {len(groups['emerging'])}개"
    )
    print("참고: 후보 점수는 자동 선정의 보조 지표이며, 발행 전 자료 검증이 필요합니다.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
