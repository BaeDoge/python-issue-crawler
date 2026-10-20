
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
import os

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
# ============================================================
# 설정
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
ENGINE_PATH = ROOT_DIR / "engine.py"

DEFAULT_TROUBLESHOOTING_COUNT = 5
DEFAULT_ALGORITHM_COUNT = 5
DEFAULT_MAX_ATTEMPTS = 20

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".next",
}


# ============================================================
# MDX 파일 탐색
# ============================================================

def find_mdx_files() -> set[Path]:
    """프로젝트 내부의 MDX 파일을 상대 경로 기준으로 반환한다."""
    files: set[Path] = set()

    for path in ROOT_DIR.rglob("*.mdx"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue

        if path.is_file():
            files.add(path.relative_to(ROOT_DIR))

    return files


# ============================================================
# 기존 엔진 실행
# ============================================================

def run_engine(topic: str) -> int:
    """기존 engine.py를 발행 없이 실행하고 로그를 출력한다."""
    command = [
        sys.executable,
        str(ENGINE_PATH),
        "--topic",
        topic,
        "--no-publish",
    ]

    print("\n" + "=" * 72, flush=True)
    print(f"[실행] 주제: {topic}", flush=True)
    print(f"[명령] {' '.join(command)}", flush=True)
    print("=" * 72, flush=True)

    try:
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        if result.stdout:
            print(result.stdout, flush=True)

        if result.returncode != 0:
            print(
                f"[오류] 엔진 종료 코드: {result.returncode}",
                flush=True,
            )
        else:
            print("[완료] 엔진 프로세스 정상 종료", flush=True)

        return result.returncode

    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(
            f"[오류] 엔진 실행 실패: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return -1


# ============================================================
# 카테고리별 생성
# ============================================================

def generate_topic(
    topic: str,
    target: int,
    max_attempts: int,
) -> tuple[int, int]:
    """신규 MDX 파일이 목표 개수에 도달할 때까지 엔진을 실행한다."""
    initial_files = find_mdx_files()
    attempts = 0

    while attempts < max_attempts:
        new_files = find_mdx_files() - initial_files
        created_count = len(new_files)

        if created_count >= target:
            break

        attempts += 1

        print(
            f"\n[{topic}] 진행 상황: {created_count}/{target}개 "
            f"(시도 {attempts}/{max_attempts})",
            flush=True,
        )

        run_engine(topic)

        # 엔진 실행 후 결과 확인
        time.sleep(1)

        current_files = find_mdx_files()
        new_files = current_files - initial_files

        print(
            f"[{topic}] 현재 신규 MDX: "
            f"{len(new_files)}/{target}개",
            flush=True,
        )

        if new_files:
            print("[신규 파일 목록]", flush=True)
            for path in sorted(new_files):
                print(f"  - {path}", flush=True)

    final_files = find_mdx_files() - initial_files
    created_count = len(final_files)

    print("\n" + "-" * 60)
    print(f"[{topic}] 결과: {created_count}/{target}개")
    print(f"[{topic}] 엔진 실행 횟수: {attempts}회")
    print("-" * 60)

    if created_count < target:
        print(
            f"[주의] 목표보다 {target - created_count}개 부족합니다. "
            "엔진 로그에서 수집 실패, 검증 실패, API 오류 등을 확인하세요.",
            flush=True,
        )

    return created_count, attempts


# ============================================================
# 메인 실행
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="알고리즘 및 트러블슈팅 MDX 자동 생성"
    )

    parser.add_argument(
        "--troubleshooting",
        type=int,
        default=DEFAULT_TROUBLESHOOTING_COUNT,
        help="생성할 트러블슈팅 글 개수 (기본값: 5)",
    )

    parser.add_argument(
        "--algorithm",
        type=int,
        default=DEFAULT_ALGORITHM_COUNT,
        help="생성할 알고리즘 글 개수 (기본값: 5)",
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help="카테고리별 최대 엔진 실행 횟수 (기본값: 20)",
    )

    args = parser.parse_args()

    if args.troubleshooting < 0 or args.algorithm < 0:
        parser.error("생성 개수는 0 이상이어야 합니다.")

    if args.max_attempts < 1:
        parser.error("--max-attempts는 1 이상이어야 합니다.")

    if not ENGINE_PATH.is_file():
        print(f"[오류] 엔진 파일을 찾을 수 없습니다: {ENGINE_PATH}")
        print("batch.py와 engine.py가 같은 디렉터리에 있는지 확인하세요.")
        return 1

    print("=" * 72)
    print("MDX 자동 생성 시작")
    print(f"프로젝트 경로: {ROOT_DIR}")
    print(f"엔진 경로: {ENGINE_PATH}")
    print(f"트러블슈팅 목표: {args.troubleshooting}개")
    print(f"알고리즘 목표: {args.algorithm}개")
    print(f"카테고리별 최대 시도: {args.max_attempts}회")
    print("발행: 비활성화 (--no-publish)")
    print("=" * 72, flush=True)

    results: dict[str, tuple[int, int]] = {}

    try:
        jobs = [
            ("troubleshooting", args.troubleshooting),
            ("algorithm", args.algorithm),
        ]

        for topic, target in jobs:
            if target == 0:
                results[topic] = (0, 0)
                print(f"\n[{topic}] 생성 건수가 0이므로 건너뜁니다.")
                continue

            results[topic] = generate_topic(
                topic=topic,
                target=target,
                max_attempts=args.max_attempts,
            )

    except KeyboardInterrupt:
        print("\n[중단] 사용자 요청으로 작업을 중단했습니다.")

    print("\n" + "=" * 72)
    print("최종 요약")
    print("=" * 72)

    total_created = 0

    for topic, (created, attempts) in results.items():
        target = (
            args.troubleshooting
            if topic == "troubleshooting"
            else args.algorithm
        )

        total_created += created

        print(
            f"{topic}: {created}/{target}개 "
            f"(엔진 실행 {attempts}회)"
        )

    print(f"신규 MDX 파일 합계: {total_created}개")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    exit_code = 1

    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("\n[중단] 작업이 중단되었습니다.")
    except Exception as exc:
        print(
            f"\n[치명적 오류] {type(exc).__name__}: {exc}",
            flush=True,
        )
        import traceback
        traceback.print_exc()

    try:
        input("\n실행이 종료되었습니다. Enter를 누르면 창이 닫힙니다...")
    except (EOFError, KeyboardInterrupt):
        pass

    sys.exit(exit_code)
