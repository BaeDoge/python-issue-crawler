"""
발행 — 대상(Target) 레포에 mdx(+영문판+이미지)를 커밋하고 push합니다. Vercel 등은 push를 감지해 자동 배포.
========================================================================
- 한 번의 커밋에 한국어 mdx, 영문 mdx(대상에 en_posts_dir가 있을 때), 이미지가 함께 들어갑니다.
- mode="immediate": 글마다 push / mode="batch": 로컬 커밋만 쌓고 push_interval_minutes마다 한꺼번에 push
  (연속 생성 시 배포 횟수를 줄이기 위함 — Vercel Hobby는 하루 배포 횟수 제한이 있습니다).
- 대상별 daily_limit, 허가 대기(hold_third_party) 같은 규칙은 pubqueue.is_eligible/publish_eligible이 처리합니다.

전제: 각 레포 경로에서 `git push`가 추가 인증 없이 되어야 합니다(SSH 키 또는 credential helper).
"""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pubqueue
from config import OUTPUT_DIR
from targets import Target, load_targets

STATE_PATH = OUTPUT_DIR / "publish_state.json"


class PublishError(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise PublishError(f"git {' '.join(args)} 실패:\n{r.stderr.strip()}")
    return r.stdout.strip()


def _repo_ok(target: Target):
    if not (target.repo_path / ".git").exists():
        return f"[{target.name}] {target.repo_path}가 git 레포가 아닙니다 (clone이 안 된 경로일 수 있음)."
    return None


def _state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _set_last_push(name: str) -> None:
    st = _state()
    st[name] = {"last_push": datetime.now().isoformat(timespec="seconds")}
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def publish_note(meta_path: Path, target: Target) -> dict:
    """노트 하나를 target 레포에 커밋(immediate 모드면 push까지). 반환: {"ok","committed","pushed","message"}"""
    fail = lambda msg: {"ok": False, "committed": False, "pushed": False, "message": msg}
    problem = _repo_ok(target)
    if problem:
        return fail(problem)

    meta = pubqueue.load_meta(meta_path)
    mdx = pubqueue.mdx_path_of(meta_path)
    repo = target.repo_path

    try:
        _git(repo, "checkout", target.branch)
        _git(repo, "pull", "--rebase", "--autostash", "origin", target.branch)
    except PublishError as e:
        return fail(f"[{target.name}] 레포 동기화 실패(충돌 가능성) — 수동으로 확인해주세요: {e}")

    posts_dir = repo / target.posts_dir
    posts_dir.mkdir(parents=True, exist_ok=True)
    to_add = []

    dest = posts_dir / mdx.name
    shutil.copyfile(mdx, dest)
    to_add.append(dest)

    en = pubqueue.en_path_of(meta_path)
    if target.wants_english:
        if en.exists():
            en_dir = repo / target.en_posts_dir
            en_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(en, en_dir / en.name)
            to_add.append(en_dir / en.name)
        else:
            print(f"[{target.name}] 영문판이 없어 한국어만 발행합니다 (번역 실패였거나 en 설정 전에 만든 글).")

    for img in meta.get("image_files", []):
        src = Path(img["local_path"])
        if src.exists():
            d = repo / img["repo_path"]
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, d)
            to_add.append(d)

    try:
        for f in to_add:
            _git(repo, "add", str(f.relative_to(repo)))
        if not _git(repo, "status", "--porcelain"):
            return {"ok": True, "committed": False, "pushed": False, "message": f"[{target.name}] 변경사항 없음"}
        _git(repo, "commit", "-m", f"chore(blog): add {meta.get('content_type', 'note')} post - {meta.get('title', mdx.stem)}")
    except PublishError as e:
        return fail(f"[{target.name}] {e}")

    rel = dest.relative_to(repo)
    if target.mode == "batch" or not target.auto_push:
        why = "batch 모드 — 묶어서 push 예정" if target.mode == "batch" and target.auto_push else "auto_push=false"
        return {"ok": True, "committed": True, "pushed": False, "message": f"[{target.name}] 커밋 완료({why}): {rel}"}

    return _push(target, f"[{target.name}] push 완료 — 배포가 곧 시작됩니다: {rel}")


def _push(target: Target, ok_message: str) -> dict:
    try:
        _git(target.repo_path, "push", "origin", target.branch)
    except PublishError as e:
        return {"ok": True, "committed": True, "pushed": False,
                "message": f"[{target.name}] 커밋은 됐지만 push 실패 — 직접 push 해주세요: {e}"}
    _set_last_push(target.name)
    return {"ok": True, "committed": True, "pushed": True, "message": ok_message}


def unpushed_count(target: Target) -> int:
    if _repo_ok(target):
        return 0
    try:
        _git(target.repo_path, "fetch", "origin", target.branch)
        return int(_git(target.repo_path, "rev-list", "--count", f"origin/{target.branch}..HEAD") or 0)
    except (PublishError, ValueError):
        return 0


def flush_batches(targets=None, force: bool = False) -> list:
    """batch 대상에 쌓인 커밋을 push한다. 마지막 push 후 push_interval_minutes가 지났을 때만(force면 즉시)."""
    messages = []
    for t in (targets if targets is not None else load_targets()):
        if t.mode != "batch" or not t.auto_push:
            continue
        n = unpushed_count(t)
        if n == 0:
            continue
        last = _state().get(t.name, {}).get("last_push")
        due = force or not last or (datetime.now() - datetime.fromisoformat(last)).total_seconds() >= t.push_interval_minutes * 60
        if due:
            messages.append(_push(t, f"[{t.name}] 커밋 {n}개를 한꺼번에 push했습니다 — 배포가 곧 시작됩니다")["message"])
    return messages


def publish_eligible(targets=None) -> list:
    """자격 있는 노트를 대상별 daily_limit까지 발행한다. 반환: 결과 메시지 목록."""
    messages = []
    for t in (targets if targets is not None else load_targets()):
        if not t.auto_publish:
            continue
        remaining = (t.daily_limit - pubqueue.published_today(t.name)) if t.daily_limit > 0 else 10**9
        if remaining <= 0:
            continue
        for mp in pubqueue.eligible_notes(t)[:remaining]:
            res = publish_note(mp, t)
            messages.append(res["message"])
            if res["committed"]:
                pubqueue.mark_published(mp, t.name)
            if not res["ok"]:
                break
    messages += flush_batches(targets)
    return messages
