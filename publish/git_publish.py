"""
Publish generated MDX to the standalone blog and portfolio repositories.
Each destination is committed/pushed independently so one failed target does not
prevent the other target from being published.
"""

import shutil
import subprocess
from pathlib import Path

from config import (
    AUTO_PUSH,
    BLOG_CONTENT_DIR,
    BLOG_GIT_BRANCH,
    BLOG_REPO_PATH,
    PORTFOLIO_GIT_BRANCH,
    PORTFOLIO_REPO_PATH,
    POSTS_SUBDIR,
)


class PublishError(Exception):
    pass


def _run_git(repo_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "상세 오류 메시지 없음").strip()
        raise PublishError(f"git {' '.join(args)} 실패:\n{detail}")
    return (result.stdout or "").strip()


def _publish_to_repo(
    *,
    repo_path: Path | None,
    branch: str,
    relative_post_path: Path,
    note_path: Path,
    title: str,
    content_type: str,
    image_files: list | None,
    destination_label: str,
) -> dict:
    result = {
        "target": destination_label,
        "ok": False,
        "committed": False,
        "pushed": False,
        "message": "",
    }
    if repo_path is None:
        result["message"] = f"{destination_label}: 경로 설정이 없어 건너뜀"
        return result
    if not (repo_path / ".git").exists():
        result["message"] = f"{destination_label}: {repo_path}가 git 레포가 아닙니다."
        return result
    if not note_path.exists():
        result["message"] = f"생성된 MDX 파일을 찾을 수 없습니다: {note_path}"
        return result

    try:
        # Keep publishing deterministic. A dirty target checkout should be resolved
        # by the owner rather than risking an accidental branch switch.
        dirty = _run_git(repo_path, "status", "--porcelain")
        if dirty:
            result["message"] = (
                f"{destination_label}: 작업 트리에 미커밋 변경이 있어 중단했습니다. "
                "대상 저장소의 변경사항을 먼저 커밋하거나 정리해주세요."
            )
            return result

        _run_git(repo_path, "fetch", "origin", branch)
        _run_git(repo_path, "checkout", branch)
        _run_git(repo_path, "pull", "--ff-only", "origin", branch)

        dest_path = repo_path / relative_post_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(note_path, dest_path)

        copied_images = []
        for image in image_files or []:
            src = Path(image.get("local_path", ""))
            relative_image = Path(image.get("repo_path", ""))
            if not src.is_file() or not relative_image.parts or relative_image.is_absolute() or ".." in relative_image.parts:
                continue
            image_dest = repo_path / relative_image
            image_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, image_dest)
            copied_images.append(image_dest)

        _run_git(repo_path, "add", "--", str(dest_path.relative_to(repo_path)))
        for image_dest in copied_images:
            _run_git(repo_path, "add", "--", str(image_dest.relative_to(repo_path)))

        staged = _run_git(repo_path, "diff", "--cached", "--name-only")
        if not staged:
            result["ok"] = True
            result["message"] = f"{destination_label}: 변경사항 없음"
            return result

        _run_git(repo_path, "commit", "-m", f"chore(blog): add {content_type} post - {title}")
        result["committed"] = True

        if not AUTO_PUSH:
            result["ok"] = True
            result["message"] = f"{destination_label}: 로컬 커밋 완료 (AUTO_PUSH=false)"
            return result

        _run_git(repo_path, "push", "origin", branch)
        result["ok"] = True
        result["pushed"] = True
        result["message"] = f"{destination_label}: push 완료 — Vercel 자동 배포가 시작됩니다 ({relative_post_path})"
        return result

    except (PublishError, OSError, shutil.Error) as exc:
        result["message"] = f"{destination_label}: 발행 실패: {exc}"
        return result


def publish_note(
    note_path: Path,
    *,
    title: str,
    content_type: str,
    image_files: list | None = None,
) -> dict:
    """Publish the same note to each configured target, reporting partial failures."""
    content_type = (content_type or "troubleshooting").strip().lower()
    category = {
        "algorithm": "algorithm",
        "troubleshooting": "troubleshooting",
    }.get(content_type, "troubleshooting")

    targets = []
    if BLOG_REPO_PATH is not None:
        targets.append(_publish_to_repo(
            repo_path=BLOG_REPO_PATH,
            branch=BLOG_GIT_BRANCH,
            relative_post_path=Path(BLOG_CONTENT_DIR) / category / note_path.name,
            note_path=note_path,
            title=title,
            content_type=content_type,
            image_files=image_files,
            destination_label="기술 블로그",
        ))
    if PORTFOLIO_REPO_PATH is not None:
        targets.append(_publish_to_repo(
            repo_path=PORTFOLIO_REPO_PATH,
            branch=PORTFOLIO_GIT_BRANCH,
            relative_post_path=Path(POSTS_SUBDIR) / note_path.name,
            note_path=note_path,
            title=title,
            content_type=content_type,
            image_files=image_files,
            destination_label="포트폴리오",
        ))

    if not targets:
        message = (
            "BLOG_REPO_PATH와 PORTFOLIO_REPO_PATH가 모두 설정되지 않았습니다. "
            "글은 로컬 output_files에만 저장됐습니다."
        )
        return {
            "ok": False, "committed": False, "pushed": False,
            "targets": [], "message": message,
        }

    successes = [target for target in targets if target["ok"]]
    pushed = [target for target in targets if target["pushed"]]
    messages = [target["message"] for target in targets]
    return {
        "ok": len(successes) == len(targets),
        "committed": any(target["committed"] for target in targets),
        "pushed": bool(pushed),
        "targets": targets,
        "message": "\n".join(messages),
    }
