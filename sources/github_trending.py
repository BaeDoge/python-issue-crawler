"""GitHub 인기/트렌딩 저장소 후보 수집기.

GITHUB_SSL_VERIFY=false가 기본값입니다. TLS 검증을 끈 경우 토큰은 전송하지 않습니다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from requests.exceptions import RequestException

from config import LOG_DIR, OUTPUT_DIR

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



def _candidate_snapshot_dir() -> Path:
    path = LOG_DIR / "github_candidates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _migrate_and_prune_candidate_snapshots() -> None:
    """Move legacy candidate snapshots out of output_files and retain only a small recent set."""
    snapshot_dir = _candidate_snapshot_dir()

    # 이전 버전이 output_files에 남긴 후보 스냅샷은 삭제하지 않고 로그 폴더로 이동합니다.
    if OUTPUT_DIR.exists():
        for legacy in OUTPUT_DIR.glob("github_opensource_candidates_*.json"):
            destination = snapshot_dir / legacy.name
            try:
                if destination.exists():
                    legacy.unlink()
                else:
                    shutil.move(str(legacy), str(destination))
            except OSError as exc:
                print(f"[GitHub] 이전 후보 JSON 정리 경고({legacy.name}): {exc}")

    try:
        keep_count = max(0, int(os.getenv("GITHUB_CANDIDATE_SNAPSHOT_KEEP", "5")))
    except ValueError:
        keep_count = 5
    snapshots = sorted(
        snapshot_dir.glob("github_opensource_candidates_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in snapshots[keep_count:]:
        try:
            old.unlink()
        except OSError as exc:
            print(f"[GitHub] 오래된 후보 JSON 정리 경고({old.name}): {exc}")


def _save_candidate_snapshot(payload: dict) -> Path | None:
    """Keep candidate discovery artifacts under logs, not beside generated blog posts."""
    _migrate_and_prune_candidate_snapshots()
    if os.getenv("GITHUB_SAVE_CANDIDATE_SNAPSHOTS", "false").strip().lower() in {"0", "false", "no"}:
        print("[GitHub] 후보 JSON 스냅샷 저장 비활성화됨 (GITHUB_SAVE_CANDIDATE_SNAPSHOTS=false)")
        return None

    output_path = _candidate_snapshot_dir() / (
        f"github_opensource_candidates_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
    )
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _migrate_and_prune_candidate_snapshots()
    return output_path


def _catalog_readme_excerpt(text: str, max_chars: int) -> str:
    """Summarize a large README across its sections rather than truncating at the beginning."""
    if len(text) <= max_chars:
        return text

    lines = text.splitlines()
    first_heading = next((i for i, line in enumerate(lines) if re.match(r"^#{2,4}\s+", line)), len(lines))
    intro = "\n".join(lines[:first_heading]).strip()
    intro_limit = min(2_000, max_chars // 5)
    if len(intro) > intro_limit:
        intro = intro[:intro_limit].rsplit("\n", 1)[0] + "\n[도입부 일부 생략]"

    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines[first_heading:]:
        if re.match(r"^#{1,4}\s+", line):
            if current:
                sections.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        sections.append(current)

    blocks: list[str] = []
    for section in sections:
        heading = section[0].strip()
        entries: list[str] = []
        for line in section[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            is_link = bool(re.search(r"\[[^\]]+\]\(https?://[^)]+\)", stripped))
            is_list = stripped.startswith(("- ", "* ", "+ "))
            # A sentence is useful for prose sections; link/list lines are preferred for catalogs.
            if is_link or is_list or not entries:
                entries.append(stripped)
            if len(entries) >= 3:
                break
        if entries:
            block = "\n".join([heading, *entries])
            blocks.append(block[:420])

    base = intro
    note = "[README가 길어 섹션 전반의 대표 항목을 발췌했습니다. 전체 목록을 의미하지 않습니다.]"
    remaining = max_chars - len(base) - len(note) - 8
    if remaining <= 0 or not blocks:
        return (base + "\n\n" + note)[:max_chars]

    # Select evenly spaced sections so later categories do not disappear from the evidence.
    average_block_budget = 330
    capacity = max(1, min(len(blocks), remaining // average_block_budget))
    if capacity == 1:
        indices = [len(blocks) // 2]
    else:
        indices = sorted({
            round(i * (len(blocks) - 1) / (capacity - 1))
            for i in range(capacity)
        })

    selected = [blocks[index] for index in indices]
    output = [base, note]
    used = sum(len(part) for part in output) + 4
    for block in selected:
        if used + len(block) + 2 > max_chars:
            continue
        output.append(block)
        used += len(block) + 2
    return "\n\n".join(part for part in output if part)[:max_chars]


def _code_excerpt(path: str, text: str, max_chars: int) -> str:
    """Keep representative definitions from the beginning, middle, and end of large source files."""
    if len(text) <= max_chars:
        return text

    lines = text.splitlines()
    if not lines:
        return text[:max_chars]

    definition_re = re.compile(
        r"^\s*(?:class\s+\w+|struct\s+\w+|enum\s+\w+|"
        r"(?:async\s+)?def\s+\w+|fn\s+\w+|func\s+\w+|"
        r"(?:TF|TFE)_[A-Za-z0-9_]+\s*\(|"
        r"(?:public|private|protected|static)\s+.*\(|"
        r"if\s+__name__\s*==)"
    )
    starts = [index for index, line in enumerate(lines) if definition_re.search(line)]
    if not starts:
        head_budget = int(max_chars * 0.55)
        tail_budget = max_chars - head_budget - 60
        return text[:head_budget] + "\n\n[중간 코드 생략]\n\n" + text[-tail_budget:]

    # Pick fewer windows for small budgets, and spread them across definition positions.
    target_count = max(2, min(8, (max_chars - 300) // 250))
    if len(starts) <= target_count:
        sampled = starts
    else:
        indexes = sorted({
            round(i * (len(starts) - 1) / (target_count - 1))
            for i in range(target_count)
        })
        sampled = [starts[index] for index in indexes]

    windows: list[tuple[int, int]] = [
        (0, min(len(lines), max(6, int(len(lines) * 0.05)))),
    ]
    for center in sampled:
        windows.append((max(0, center - 3), min(len(lines), center + 9)))
    windows.append((max(0, len(lines) - max(6, int(len(lines) * 0.05))), len(lines)))

    merged: list[tuple[int, int]] = []
    for left, right in sorted(windows):
        if merged and left <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))

    output: list[str] = []
    used = 0
    for left, right in merged:
        block = "\n".join(lines[left:right])
        marker = "\n[... 중간 코드 생략 ...]\n" if output else ""
        allowance = max_chars - used - len(marker)
        if allowance <= 0:
            break
        if len(block) > allowance:
            if allowance >= 120:
                output.extend([marker, block[:allowance]])
                used = max_chars
            break
        if marker:
            output.append(marker)
            used += len(marker)
        output.append(block)
        used += len(block)

    return "".join(output)[:max_chars] if output else text[:max_chars]

def _source_excerpt(path: str, text: str, max_chars: int) -> str:
    """Use broader excerpts for long docs and stratified excerpts for source code."""
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    code_extensions = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h")
    if name in {"readme.md", "readme.rst", "readme"}:
        return _catalog_readme_excerpt(text, max_chars)
    if lower.endswith(code_extensions):
        return _code_excerpt(path, text, max_chars)
    if len(text) <= max_chars:
        return text
    if name in {"security.md", "contributing.md", "architecture.md"}:
        head = int(max_chars * 0.65)
        tail = max_chars - head
        return text[:head] + "\n\n[중간 내용 일부 생략]\n\n" + text[-tail:]
    return text[:max_chars]

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
    output_path = _save_candidate_snapshot(payload)
    if output_path:
        print(f"\n후보 스냅샷 저장: {output_path}")
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
    tree_complete = False
    file_texts: list[tuple[str, str]] = []
    try:
        tree_payload = _request(
            f"{API_ROOT}/repos/{quote(full_name, safe='/')}/git/trees/{quote(branch, safe='')}?recursive=1"
        )
        tree_paths = [
            entry.get("path", "") for entry in tree_payload.get("tree", [])
            if entry.get("type") == "blob" and entry.get("path")
        ]
        tree_complete = not bool(tree_payload.get("truncated", False))
    except (RequestException, ValueError) as exc:
        print(f"[GitHub] 파일 트리 조회 실패(메타데이터로 계속 진행): {exc}")

    # README뿐 아니라 라이선스/설계 문서, 대표 예제 문서, 실제 구현 파일을 별도로 고릅니다.
    preferred_exact = [
        "README.md", "README.rst", "README",
        "LICENSE.txt", "LICENSE", "LICENSE.md", "COPYING", "COPYING.md",
        "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml",
        "build.gradle", "Dockerfile", "SECURITY.md", "CONTRIBUTING.md",
        "ARCHITECTURE.md", "docs/architecture.md",
    ]
    preferred_rank = {
        "README.md": 0, "README.rst": 0, "README": 0,
        "LICENSE.txt": 1, "LICENSE": 1, "LICENSE.md": 1, "COPYING": 1, "COPYING.md": 1,
        "SECURITY.md": 2, "SECURITY": 2,
        "pyproject.toml": 3, "package.json": 3, "Cargo.toml": 3, "go.mod": 3,
        "pom.xml": 3, "build.gradle": 3, "Dockerfile": 3,
        "CONTRIBUTING.md": 4, "ARCHITECTURE.md": 4, "docs/architecture.md": 4,
    }
    selected_paths = sorted(
        (path for path in preferred_exact if path in tree_paths),
        key=lambda path: (preferred_rank.get(path, 10), path.lower()),
    )[:5]

    code_extensions = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h")
    ignored_parts = (
        "node_modules/", "vendor/", "dist/", "build/", "target/", "generated/",
        "coverage/", ".git/", "third_party/", "site-packages/", "package-lock",
        "pnpm-lock", "yarn.lock", ".lock",
    )

    def _path_score(path: str) -> int:
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        score = 0
        if lower.startswith(("src/", "lib/", "app/")) or "/src/" in lower or "/lib/" in lower:
            score += 50
        if lower.startswith(("solutions/", "examples/", "example/")) or any(
            marker in lower for marker in ("/solutions/", "/examples/", "/example/")
        ):
            score += 45
        if any(word in lower for word in (
            "main.", "core.", "engine.", "client.", "server.", "parser.", "agent.",
            "api.", "service.", "database.", "cache.", "pipeline.", "gpt", "llm",
            "tokenizer", "attention", "transformer", "train", "generate", "inference",
            "c_api", "security", "safety", "session", "model", "runtime",
        )):
            score += 35
        if any(word in lower for word in ("test_", "_test.", ".spec.", ".test.")):
            score -= 35
        if name in {"__init__.py", "index.js", "index.ts", "index.tsx"}:
            score -= 5
        return score

    code_candidates = [
        p for p in tree_paths
        if p.lower().endswith(code_extensions)
        and not any(part in p.lower() for part in ignored_parts)
        and len(p) < 180
    ]
    code_candidates.sort(key=lambda p: (-_path_score(p), len(p), p.lower()))

    # 프로젝트 소스/예제의 서로 다른 디렉터리에서 최대 3개 구현 파일을 가져옵니다.
    chosen_code_dirs = set()
    for path in code_candidates:
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent in chosen_code_dirs or path in selected_paths:
            continue
        selected_paths.append(path)
        chosen_code_dirs.add(parent)
        if len(chosen_code_dirs) >= 3:
            break

    # 튜토리얼/설계 가이드가 핵심인 저장소도 있으므로, 대표 예제 문서를 최대 2개 보충합니다.
    example_docs = [
        p for p in tree_paths
        if p.lower().endswith((".md", ".mdx", ".rst"))
        and p not in selected_paths
        and (
            any(marker in p.lower() for marker in (
                "/solutions/", "/examples/", "/example/", "/docs/",
            ))
            or (
                p.lower().endswith("/readme.md")
                and p.split("/", 1)[0].startswith(("ch", "appendix-", "setup"))
            )
        )
        and not any(token in p.lower() for token in (
            "readme-ja", "readme-zh", "readme-ko", "readme-zh-tw", "translation",
            "changelog", "release-notes",
        ))
        and len(p) < 180
    ]
    def _example_doc_priority(path: str) -> tuple[int, int, str]:
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        first_dir = path.split("/", 1)[0]
        if parent in chosen_code_dirs:
            rank = 0
        elif first_dir == "ch04":
            rank = 1
        elif first_dir.startswith("appendix-"):
            rank = 2
        elif first_dir.startswith("ch"):
            rank = 3
        else:
            rank = 4
        return (rank, len(path), path.lower())

    example_docs.sort(key=_example_doc_priority)
    chosen_doc_dirs = set()
    for path in example_docs:
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent in chosen_doc_dirs:
            continue
        selected_paths.append(path)
        chosen_doc_dirs.add(parent)
        if len(chosen_doc_dirs) >= 2:
            break

    # 긴 저장소에서도 컨텍스트 크기를 제한하고, tree path만 보고 내부 동작을 추정하지 않습니다.
    selected_paths = selected_paths[:10]

    # Keep the writer prompt bounded. A long catalog README receives a sampled excerpt
    # from across its sections; code/config files receive focused excerpts.
    used_chars = 0
    for path in selected_paths:
        url = f"https://raw.githubusercontent.com/{full_name}/{quote(branch, safe='')}/{quote(path, safe='/')}"
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        if "/" not in path and name in {"readme.md", "readme.rst", "readme"}:
            file_budget = 13_000
        elif lower.endswith(code_extensions):
            file_budget = 5_600
        elif "license" in name or name.startswith("copying"):
            file_budget = 3_000
        elif name in {"security.md", "contributing.md", "architecture.md"}:
            file_budget = 3_200
        elif name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml", "build.gradle"}:
            file_budget = 2_600
        else:
            file_budget = 2_600
        remaining_budget = 42_000 - used_chars
        if remaining_budget < 700:
            break
        file_budget = min(file_budget, remaining_budget)
        try:
            response = SESSION.get(url, timeout=20, verify=SSL_VERIFY)
            if response.status_code == 200 and len(response.text) < 180_000:
                excerpt = _source_excerpt(path, response.text, file_budget)
                file_texts.append((path, excerpt))
                used_chars += len(excerpt) + len(path) + 80
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
        "\n".join(f"- {p}" for p in tree_paths[:120]) or "파일 트리를 가져오지 못했습니다.",
        "",
        "추가로 수집한 공식 저장소 파일(원문 자료, 그대로 복사하지 말 것):",
    ]
    for path, text_content in file_texts:
        file_url = f"https://github.com/{full_name}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}"
        parts.extend(["", f"--- FILE: {path} ---", f"공식 파일 URL: {file_url}", text_content])
    # Reviewer에게도 원문 근거를 전달해야 추측성 지적을 줄일 수 있습니다.
    # 파일 경로 목록은 존재 여부만 나타내며, 실제 파일 내용과 구분해 제공합니다.
    top_level_names = sorted({path.split("/", 1)[0] for path in tree_paths if path})
    review_parts = [
        f"저장소: {repo.get('full_name', full_name)}",
        f"공식 URL: {repo.get('html_url', candidate.get('link', ''))}",
        f"기본 브랜치: {branch}",
        f"파일 트리 전체 확인: {'예' if tree_complete else '아니오(잘렸거나 조회 실패)'}",
        f"생성일: {repo.get('created_at', '미확인')} / 최근 push: {repo.get('pushed_at', '미확인')}",
        f"GitHub 라이선스 메타데이터(SPDX; 원문 LICENSE와 별개): {license_info.get('spdx_id') or '미확인'}",
        "최상위 파일/디렉터리 이름(트리에서 추출):",
        "\n".join(f"- {name}" for name in top_level_names[:80]) or "파일 트리를 가져오지 못했습니다.",
        "",
        "실제로 다운로드한 공식 파일 경로:",
        "\n".join(f"- {path}" for path, _ in file_texts),
        "",
        "실제로 다운로드한 공식 파일 원문 발췌:",
    ]
    review_budget = 24_000 - sum(len(part) for part in review_parts)

    code_extensions_for_review = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h")

    def _review_file_priority(path: str) -> tuple[int, int, str]:
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        is_root = "/" not in path
        if is_root and name in {"readme.md", "readme.rst", "readme"}:
            rank = 0
        elif lower.endswith(code_extensions_for_review):
            rank = 1
        elif "license" in name or name.startswith("copying"):
            rank = 2
        elif name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml", "build.gradle"}:
            rank = 3
        elif name == "readme.md":
            rank = 4
        else:
            rank = 5
        return (rank, len(path), path.lower())

    def _review_excerpt_limit(path: str) -> int:
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        if "/" not in path and name in {"readme.md", "readme.rst", "readme"}:
            return 3_400
        if lower.endswith(code_extensions_for_review):
            return 3_200
        if "license" in name or name.startswith("copying"):
            return 2_200
        if name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml", "build.gradle"}:
            return 2_000
        if name == "readme.md":
            return 1_300
        return 1_600

    code_excerpt_count = 0
    document_excerpt_count = 0
    for path, text_content in sorted(file_texts, key=lambda item: _review_file_priority(item[0])):
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        is_code = lower.endswith(code_extensions_for_review)
        is_nested_readme = name == "readme.md" and "/" in path

        # 한 종류의 자료만 컨텍스트를 차지하지 않도록, 리뷰용 코드와 하위 문서는 각각 2개까지만 포함합니다.
        if is_code and code_excerpt_count >= 2:
            continue
        if is_nested_readme and document_excerpt_count >= 2:
            continue
        if review_budget <= 500:
            break
        allowance = min(_review_excerpt_limit(path), review_budget)
        if allowance < 400:
            break
        snippet = _source_excerpt(path, text_content, allowance)
        file_url = f"https://github.com/{full_name}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}"
        review_parts.extend(["", f"--- {path} (원문 발췌) ---", f"공식 파일 URL: {file_url}", snippet])
        review_budget -= len(path) + len(snippet) + 20
        if is_code:
            code_excerpt_count += 1
        if is_nested_readme:
            document_excerpt_count += 1

    return {
        "context_text": "\n".join(parts),
        "review_context": "\n".join(review_parts),
        "tree_paths": tree_paths,
        "tree_complete": tree_complete,
        "source_file_count": len(file_texts),
        "analysis_source_count": sum(
            1 for path, text_content in file_texts
            if len(text_content.strip()) >= 200
            and not any(token in path.rsplit("/", 1)[-1].lower() for token in ("license", "copying", "notice"))
        ),
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

