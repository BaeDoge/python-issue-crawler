"""
발행 이력 — 같은 소재를 매일 반복해서 쓰지 않도록 이미 다룬 원문 링크를 기록합니다.
========================================================================
output_files/history.json에 {topic_key: [{"link","title","at"}]} 형태로 저장합니다.
다시 쓰고 싶은 소재가 있으면 해당 항목을 이 파일에서 지우면 됩니다.
"""

import json
from datetime import datetime

from config import OUTPUT_DIR

HISTORY_PATH = OUTPUT_DIR / "history.json"


def _load() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def is_used(topic_key: str, link: str | None) -> bool:
    if not link:
        return False
    return any(item.get("link") == link for item in _load().get(topic_key, []))


def mark_used(topic_key: str, link: str | None, title: str) -> None:
    if not link:
        return
    data = _load()
    data.setdefault(topic_key, []).append({
        "link": link, "title": title, "at": datetime.now().isoformat(timespec="seconds"),
    })
    HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
