"""
포트폴리오 레포에 커밋 + 푸시 — Vercel이 push를 감지해서 자동 배포합니다.
========================================================================
⚠️ 기본값은 AUTO_PUSH=true(즉시 push, 바로 라이브 배포)입니다. 이게 부담스러우면
.env에서 AUTO_PUSH=false로 바꾸세요 — 그러면 로컬 커밋까지만 하고 push는 직접
`git push`로 수동 실행하게 됩니다. 커밋 자체는 로컬이라 언제든 `git reset`으로
되돌릴 수 있습니다.

전제 조건:
- PORTFOLIO_REPO_PATH가 실제로 git clone된 레포 경로여야 함
- 해당 경로에서 `git push`가 추가 인증 없이 되는 상태여야 함(SSH 키 또는
  git credential helper 설정 완료)
"""

import shutil
import subprocess
from pathlib import Path

from config import PORTFOLIO_REPO_PATH, POSTS_SUBDIR, AUTO_PUSH, GIT_BRANCH


class PublishError(Exception):
    pass



def _run_git(repo_path: Path, *args: str) -> str:
    """Git 명령을 실행하고 UTF-8 출력 및 디코딩 오류를 안전하게 처리한다."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        error_output = stderr or stdout or "상세 오류 메시지 없음"

        raise PublishError(
            f"git {' '.join(args)} 실패:\n{error_output}"
        )

    return (result.stdout or "").strip()



def publish_note(note_path: Path, *, title: str, content_type: str, image_files: list | None = None) -> dict:
    """생성된 mdx 파일을 포트폴리오 레포에 커밋(+push)한다.
    반환: {"ok": bool, "committed": bool, "pushed": bool, "message": str}"""
    if PORTFOLIO_REPO_PATH is None:
        return {"ok": False, "committed": False, "pushed": False,
                "message": "PORTFOLIO_REPO_PATH가 .env에 설정되어 있지 않습니다."}

    repo_path = PORTFOLIO_REPO_PATH
    if not (repo_path / ".git").exists():
        return {"ok": False, "committed": False, "pushed": False,
                "message": f"{repo_path}가 git 레포가 아닙니다 (clone이 안 된 경로일 수 있음)."}

    posts_dir = repo_path / POSTS_SUBDIR
    posts_dir.mkdir(parents=True, exist_ok=True)
    dest_path = posts_dir / note_path.name

    try:
        _run_git(repo_path, "checkout", GIT_BRANCH)
        _run_git(repo_path, "pull", "--ff-only", "origin", GIT_BRANCH)
    except PublishError as e:
        return {"ok": False, "committed": False, "pushed": False,
                "message": f"레포 동기화 실패(충돌 가능성) — 수동으로 확인해주세요: {e}"}

    shutil.copyfile(note_path, dest_path)

    # 노트에 포함된 이미지 파일들도 레포의 public/blogs/ 등으로 같이 복사
    copied_images = []
    for img in (image_files or []):
        src = Path(img["local_path"])
        if not src.exists():
            continue
        img_dest = repo_path / img["repo_path"]
        img_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, img_dest)
        copied_images.append(img_dest)

    try:
        _run_git(repo_path, "add", str(dest_path.relative_to(repo_path)))
        for img_dest in copied_images:
            _run_git(repo_path, "add", str(img_dest.relative_to(repo_path)))
        status = _run_git(repo_path, "status", "--porcelain")
        if not status:
            return {"ok": True, "committed": False, "pushed": False,
                    "message": "변경사항 없음 (이미 동일한 내용이 존재)"}

        commit_msg = f"chore(blog): add {content_type} post - {title}"
        _run_git(repo_path, "commit", "-m", commit_msg)
    except PublishError as e:
        return {"ok": False, "committed": False, "pushed": False, "message": str(e)}

    if not AUTO_PUSH:
        return {"ok": True, "committed": True, "pushed": False,
                "message": f"로컬 커밋 완료. AUTO_PUSH=false라 push는 직접 해주세요 "
                           f"(cd {repo_path} && git push origin {GIT_BRANCH})."}

    try:
        _run_git(repo_path, "push", "origin", GIT_BRANCH)
    except PublishError as e:
        return {"ok": True, "committed": True, "pushed": False,
                "message": f"커밋은 됐지만 push 실패 — 직접 push 해주세요: {e}"}

    return {"ok": True, "committed": True, "pushed": True,
            "message": f"push 완료 — Vercel이 곧 자동 배포를 시작합니다. ({dest_path.relative_to(repo_path)})"}
