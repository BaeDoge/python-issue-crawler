"""
Publish generated MDX to any number of configured Git repositories.
Targets are defined in the single PUBLISH_TARGETS JSON environment variable.
"""

import re
import shutil
import subprocess
from pathlib import Path

from config import AUTO_PUSH, PUBLISH_TARGETS


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


def _safe_relative(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise PublishError(f"저장소 내부의 안전한 상대 경로가 아닙니다: {value}")
    return path


def _publish_to_repo(
    *,
    target: dict,
    note_path: Path,
    title: str,
    content_type: str,
    image_files: list | None,
    category: str,
) -> dict:
    name = target["name"]
    repo_path = target["repo_path"]
    branch = target["branch"]
    result = {"target": name, "ok": False, "committed": False, "pushed": False, "message": ""}

    if not (repo_path / ".git").exists():
        result["message"] = f"{name}: {repo_path}가 Git 저장소가 아닙니다."
        return result
    if not note_path.is_file():
        result["message"] = f"{name}: 생성된 MDX 파일을 찾을 수 없습니다: {note_path}"
        return result

    try:
        dirty = _run_git(repo_path, "status", "--porcelain")
        if dirty:
            result["message"] = (
                f"{name}: 작업 트리에 미커밋 변경이 있어 발행을 중단했습니다. "
                "대상 저장소의 변경사항을 먼저 커밋하거나 정리해주세요."
            )
            return result

        _run_git(repo_path, "fetch", "origin", branch)
        _run_git(repo_path, "checkout", branch)
        _run_git(repo_path, "pull", "--ff-only", "origin", branch)

        posts_dir = _safe_relative(target["posts_dir"])
        if target["category_subdirs"]:
            posts_dir = posts_dir / category
        dest_path = repo_path / posts_dir / note_path.name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        note_content = note_path.read_text(encoding="utf-8")
        image_url_prefix = target["image_url_prefix"]
        if image_url_prefix != "/blogs":
            note_content = re.sub(
                r"(?<=\\()/?blogs/",
                image_url_prefix + "/",
                note_content,
            )
        dest_path.write_text(note_content, encoding="utf-8", newline="\n")

        images_dir = _safe_relative(target["images_dir"])
        copied_images = []
        for image in image_files or []:
            src = Path(image.get("local_path", ""))
            if not src.is_file():
                continue
            filename = Path(image.get("repo_path", "")).name
            if not filename or filename in (".", ".."):
                continue
            image_dest = repo_path / images_dir / filename
            image_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, image_dest)
            copied_images.append(image_dest)

        staged_paths = [dest_path.relative_to(repo_path), *[p.relative_to(repo_path) for p in copied_images]]
        _run_git(repo_path, "add", "--", *[str(p) for p in staged_paths])
        staged = _run_git(repo_path, "diff", "--cached", "--name-only")
        if not staged:
            result["ok"] = True
            result["message"] = f"{name}: 변경사항 없음"
            return result

        _run_git(repo_path, "commit", "-m", f"chore(blog): add {content_type} post - {title}")
        result["committed"] = True
        if not AUTO_PUSH:
            result["ok"] = True
            result["message"] = f"{name}: 로컬 커밋 완료 (AUTO_PUSH=false)"
            return result

        _run_git(repo_path, "push", "origin", branch)
        result["ok"] = True
        result["pushed"] = True
        result["message"] = f"{name}: push 완료 — 배포 자동화가 시작됩니다 ({dest_path.relative_to(repo_path)})"
        return result

    except (PublishError, OSError, shutil.Error) as exc:
        result["message"] = f"{name}: 발행 실패: {exc}"
        return result


def publish_note(
    note_path: Path,
    *,
    title: str,
    content_type: str,
    image_files: list | None = None,
) -> dict:
    """Publish the same generated note to every configured target independently."""
    category = {
        "algorithm": "algorithm",
        "troubleshooting": "troubleshooting",
    }.get((content_type or "troubleshooting").strip().lower(), "troubleshooting")

    if not PUBLISH_TARGETS:
        return {
            "ok": False, "committed": False, "pushed": False, "targets": [],
            "message": "PUBLISH_TARGETS가 비어 있습니다. .env에 발행 대상을 하나 이상 설정해주세요.",
        }

    results = [
        _publish_to_repo(
            target=target,
            note_path=note_path,
            title=title,
            content_type=content_type,
            image_files=image_files,
            category=category,
        )
        for target in PUBLISH_TARGETS
    ]
    successes = [item for item in results if item["ok"]]
    return {
        "ok": len(successes) == len(results),
        "committed": any(item["committed"] for item in results),
        "pushed": any(item["pushed"] for item in results),
        "targets": results,
        "message": "\n".join(item["message"] for item in results),
    }
