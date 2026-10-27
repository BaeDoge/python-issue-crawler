"""
스케줄러 — 자동 생성/발행
========================================================================
    uv run pipeline/scheduler.py                 # 매일 SCHEDULE_TIME에 주제별 1편씩 생성+발행
    uv run pipeline/scheduler.py --continuous    # GPU를 쉬지 않고 계속 생성 (공개 속도는 대상별 daily_limit로 조절)

--continuous 동작:
  - 주제를 번갈아 가며 한 편씩 계속 생성합니다. 글 사이에 CONTINUOUS_COOLDOWN_SEC(기본 5초)만 쉽니다.
  - 매번 발행도 시도하지만, 대상마다 daily_limit까지만 나가고 나머지는 대기열에 쌓입니다.
    (생성은 빠르고 공개는 느리게 — 갑자기 수백 편이 올라가는 것을 막기 위함)
  - 발행 대기 글이 QUEUE_MAX_READY(기본 100)개 이상이면 생성을 멈추고 발행만 합니다(GPU 낭비 방지).
  - 모든 주제에서 연속으로 새 글을 못 만들면(소스 고갈/접속 문제) 30분 쉬었다가 다시 시도합니다.
  - 중지: output_files/STOP 파일을 만들면 진행 중인 글을 끝낸 뒤 종료합니다.

주의: StackExchange API는 키 없이는 하루 300회 제한이라 글 하나에 약 4회를 쓰는 연속 모드에선 금방
소진됩니다. 무료 키(stackapps.com에서 앱 등록)를 .env의 STACKEXCHANGE_KEY에 넣으면 하루 10,000회입니다.
"""

import os
import sys
import time
import traceback
from datetime import datetime

import schedule

import pubqueue
from config import LOG_DIR, OUTPUT_DIR, QUEUE_MAX_READY, CONTINUOUS_COOLDOWN_SEC
from engine import generate, publish_pending, run_one
from publish.git_publish import flush_batches
from targets import load_targets
from topics import TOPICS

SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "09:00").strip()
LOG_PATH = LOG_DIR / "scheduler.log"
STOP_FILE = OUTPUT_DIR / "STOP"
EXHAUSTED_SLEEP_SEC = 30 * 60
QUEUE_FULL_SLEEP_SEC = 10 * 60


def _log(msg: str):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _sleep(seconds: int) -> None:
    """STOP 파일을 확인하면서 쉰다."""
    end = time.time() + seconds
    while time.time() < end and not STOP_FILE.exists():
        time.sleep(min(5, max(0.1, end - time.time())))


def drip() -> None:
    try:
        for m in publish_pending():
            _log(m)
    except Exception:
        _log(f"발행 중 예외:\n{traceback.format_exc()}")


def daily_job():
    _log("=== 일일 자동 생성 시작 ===")
    for key in TOPICS:
        try:
            result = run_one(key, publish=True)
            _log(f"[{key}] {'성공' if result.get('ok') else '실패'}: {result.get('path', result.get('reason'))}")
        except Exception:
            _log(f"[{key}] 예외 발생:\n{traceback.format_exc()}")
    _log("=== 일일 자동 생성 종료 ===\n")


def run_daily():
    schedule.every().day.at(SCHEDULE_TIME).do(daily_job)
    schedule.every(30).minutes.do(drip)   # 어제 못 나간 대기 글을 오늘 한도 안에서 내보냄
    _log(f"스케줄러 시작 — 매일 {SCHEDULE_TIME}에 실행됩니다. (Ctrl+C로 종료) 로그: {LOG_PATH}")
    while True:
        schedule.run_pending()
        time.sleep(30)


def run_continuous():
    keys = list(TOPICS)
    if STOP_FILE.exists():
        STOP_FILE.unlink()
        _log("이전 STOP 파일을 지우고 시작합니다.")
    _log(f"연속 생성 시작 — 주제 {keys}, 쿨다운 {CONTINUOUS_COOLDOWN_SEC}초, 대기열 상한 {QUEUE_MAX_READY}. "
         f"중지: {STOP_FILE} 파일 만들기")
    i = fail_streak = error_streak = 0
    made = 0
    while not STOP_FILE.exists():
        targets = load_targets()
        if targets and pubqueue.count_waiting(targets) >= QUEUE_MAX_READY:
            _log(f"발행 대기 글이 {QUEUE_MAX_READY}개 이상이라 생성을 쉬고 발행만 합니다.")
            drip()
            _sleep(QUEUE_FULL_SLEEP_SEC)
            continue

        key = keys[i % len(keys)]
        i += 1
        try:
            result = generate(key)
            error_streak = 0
        except Exception:
            error_streak += 1
            wait = min(600, 30 * 2 ** min(error_streak, 5))
            _log(f"[{key}] 예외 발생(연속 {error_streak}회) — {wait}초 후 재시도:\n{traceback.format_exc()}")
            _sleep(wait)
            continue

        if result.get("ok"):
            made += 1
            fail_streak = 0
            _log(f"[{key}] 생성 #{made}: {result.get('path')} (검증 {'통과' if result.get('passed') else '미통과'}"
                 f"{', 영문 O' if result.get('has_en') else ''}{', 허가 대기' if result.get('has_third_party') else ''})")
        else:
            fail_streak += 1
            _log(f"[{key}] 생성 실패/스킵: {result.get('reason')} (연속 {fail_streak}회)")

        drip()

        if fail_streak >= len(keys):
            _log(f"모든 주제에서 연속으로 새 글을 못 만들었습니다(소스 고갈 또는 접속 문제) — "
                 f"{EXHAUSTED_SLEEP_SEC // 60}분 쉽니다. python engine.py --diagnose로 점검해보세요.")
            fail_streak = 0
            _sleep(EXHAUSTED_SLEEP_SEC)
        else:
            _sleep(CONTINUOUS_COOLDOWN_SEC)

    _log(f"STOP 파일이 감지되어 종료합니다. (이번 실행에서 {made}편 생성)")
    for m in flush_batches(force=True):
        _log(m)


def main():
    if "--continuous" in sys.argv:
        run_continuous()
    else:
        run_daily()


if __name__ == "__main__":
    main()
