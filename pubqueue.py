"""
발행 대기열 — 생성(GPU)과 발행(공개)의 속도를 분리합니다.
========================================================================
생성된 노트는 output_files/<주제>/<slug>.meta.json에 상태가 기록됩니다. 발행 대상(Target)마다
"자격이 있는 노트"를 골라서 daily_limit만큼만 오래된 것부터 내보냅니다. 그래서 GPU는 계속
돌리면서도, 공개되는 속도는 하루 몇 편으로 조절할 수 있습니다(검증 미통과 글, 허가 대기 글은
자격이 없어서 절대 자동으로 나가지 않음).

(파일 이름을 queue.py로 하면 파이썬 표준 라이브러리 queue와 충돌해서 pubqueue로 지었습니다.)
"""

import json
from datetime import date, datetime
from pathlib import Path

from config import OUTPUT_DIR


def meta_paths() -> list:
    return sorted(OUTPUT_DIR.glob("*/*.meta.json"), key=lambda p: p.stat().st_mtime)


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def update_meta(path: Path, **fields) -> dict:
    data = load_meta(path)
    data.update(fields)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def mdx_path_of(meta_path: Path) -> Path:
    return meta_path.with_name(meta_path.name.replace(".meta.json", ".mdx"))


def en_path_of(meta_path: Path) -> Path:
    return meta_path.parent / "en" / mdx_path_of(meta_path).name


def is_eligible(meta: dict, target) -> bool:
    if not target.auto_publish or not target.accepts(meta.get("content_type", "")):
        return False
    if not meta.get("review_passed"):
        return False                      # 검증 미통과 — 사람이 직접 확인해야 함
    if meta.get("third_party") and target.hold_third_party:
        return False                      # 다른 사람 이미지/글 참고 — 허가 전
    return target.name not in {p["target"] for p in meta.get("published", [])}


def eligible_notes(target) -> list:
    out = []
    for mp in meta_paths():
        if mdx_path_of(mp).exists() and is_eligible(load_meta(mp), target):
            out.append(mp)
    return out


def published_today(target_name: str) -> int:
    today = date.today().isoformat()
    n = 0
    for mp in meta_paths():
        for p in load_meta(mp).get("published", []):
            if p["target"] == target_name and p["at"].startswith(today):
                n += 1
    return n


def mark_published(meta_path: Path, target_name: str) -> None:
    meta = load_meta(meta_path)
    meta.setdefault("published", []).append({"target": target_name, "at": datetime.now().isoformat(timespec="seconds")})
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def count_waiting(targets) -> int:
    """어느 한 대상에라도 아직 안 나간 '자격 있는' 노트 수 — 연속 생성 모드의 과적체 방지용."""
    waiting = set()
    for t in targets:
        waiting.update(str(p) for p in eligible_notes(t))
    return len(waiting)


def summary(targets) -> dict:
    total = failed = held = 0
    for mp in meta_paths():
        m = load_meta(mp)
        total += 1
        if not m.get("review_passed"):
            failed += 1
        elif m.get("third_party"):
            held += 1
    return {"total": total, "review_failed": failed, "third_party": held,
            "waiting": {t.name: len(eligible_notes(t)) for t in targets},
            "today": {t.name: published_today(t.name) for t in targets}}
