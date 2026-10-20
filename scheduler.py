"""
스케줄러 — PC를 켜두면 매일 지정 시각에 자동으로 트러블슈팅 1편 + 알고리즘 1편을
생성해서 포트폴리오에 발행합니다.
========================================================================
실행:
    uv run pipeline/scheduler.py

껐다 켜면 그날 실행 시각이 지나있어도 다음날 예정 시각까지 기다립니다(밀린
실행을 몰아서 하지 않음). 당장 한 번 돌리고 싶으면 scheduler.py 말고
engine.py를 직접 실행하세요 — "내가 명령할 때마다"는 engine.py, "매일
자동"은 이 scheduler.py로 역할을 나눴습니다.

.env의 SCHEDULE_TIME(기본 "09:00")으로 실행 시각을 바꿀 수 있습니다.
"""

import os
import time
import traceback
from datetime import datetime

import schedule

from config import LOG_DIR
from engine import run_one
from topics import TOPICS

SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "09:00").strip()
LOG_PATH = LOG_DIR / "scheduler.log"


def _log(msg: str):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def daily_job():
    _log("=== 일일 자동 생성 시작 ===")
    for key in TOPICS:
        try:
            result = run_one(key, publish=True)
            status = "성공" if result.get("ok") else "실패"
            _log(f"[{key}] {status}: {result.get('path', result.get('reason'))}")
        except Exception:
            _log(f"[{key}] 예외 발생:\n{traceback.format_exc()}")
    _log("=== 일일 자동 생성 종료 ===\n")


def main():
    schedule.every().day.at(SCHEDULE_TIME).do(daily_job)
    _log(f"스케줄러 시작 — 매일 {SCHEDULE_TIME}에 실행됩니다. (Ctrl+C로 종료)")
    _log(f"로그 파일: {LOG_PATH}")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
