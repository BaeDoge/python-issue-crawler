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
    """A publishing error with machine-readable command diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        stage: str = "unknown",
        command: list[str] | None = None,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ):
        super().__init__(message)
        self.stage = stage
        self.command = command or []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _redact(text: str) -> str:
    """Avoid printing credentials if a remote URL unexpectedly embeds them."""
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)


def _run_git(repo_path: Path, *args: str, stage: str = "Git 명령") -> str:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        rendered = " ".join(command)
        raise PublishError(
            f"{stage} 단계에서 명령 실행 시간이 90초를 초과했습니다. "
            f"명령: {rendered}",
            stage=stage,
            command=command,
            stdout=_redact(stdout),
            stderr=_redact(stderr),
        ) from exc
    except OSError as exc:
        raise PublishError(
            f"{stage} 단계에서 Git 명령을 실행하지 못했습니다: "
            f"{type(exc).__name__}: {exc}",
            stage=stage,
            command=command,
        ) from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        detail_parts = [
            f"단계: {stage}",
            f"명령: {' '.join(command)}",
            f"종료 코드: {result.returncode}",
        ]
        if stderr:
            detail_parts.append(f"stderr:\n{_redact(stderr)}")
        if stdout:
            detail_parts.append(f"stdout:\n{_redact(stdout)}")
        if not stderr and not stdout:
            detail_parts.append("오류 출력이 비어 있습니다.")
        raise PublishError(
            "\n".join(detail_parts),
            stage=stage,
            command=command,
            returncode=result.returncode,
            stdout=_redact(stdout),
            stderr=_redact(stderr),
        )
    return stdout


def _sync_branch(repo_path: Path, branch: str) -> None:
    """Fetch and safely sync the local branch before publishing.

    Fast-forward when possible. If local and remote both contain unique commits,
    rebase local-only commits onto origin/<branch>. On conflict, abort the rebase
    so the publisher does not leave the target repository mid-rebase.
    """
    remote_ref = f"origin/{branch}"
    counts_text = _run_git(
        repo_path, "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}",
        stage="원격 브랜치와 로컬 브랜치 비교",
    )
    try:
        local_only, remote_only = (int(value) for value in counts_text.split())
    except (ValueError, TypeError) as exc:
        raise PublishError(
            f"{branch}와 {remote_ref}의 커밋 차이를 해석할 수 없습니다: {counts_text!r}",
            stage="원격 브랜치와 로컬 브랜치 비교",
        ) from exc

    if remote_only == 0:
        return

    if local_only == 0:
        _run_git(
            repo_path, "merge", "--ff-only", remote_ref,
            stage="원격 변경사항 fast-forward 반영",
        )
        return

    print(
        f"{repo_path.name}: 로컬 {branch}와 {remote_ref}가 분기되어 있습니다 "
        f"(로컬 전용 {local_only}개, 원격 전용 {remote_only}개). "
        "로컬 커밋을 원격 최신 커밋 위로 rebase합니다."
    )
    try:
        _run_git(repo_path, "rebase", remote_ref, stage="분기된 브랜치 rebase")
    except PublishError as exc:
        try:
            abort = subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
            )
            abort_detail = (
                "자동 rebase를 취소해 원래 로컬 커밋 상태로 복구했습니다."
                if abort.returncode == 0
                else "자동 rebase 취소도 완료되지 않았습니다. 추가 Git 명령을 실행하지 말고 git status로 상태를 확인하세요."
            )
        except (OSError, subprocess.SubprocessError) as abort_exc:
            abort_detail = f"자동 rebase 취소 중 추가 오류가 발생했습니다: {abort_exc}"

        raise PublishError(
            f"{branch}와 {remote_ref}의 자동 rebase에 실패했습니다. {abort_detail}\n"
            f"원인:\n{exc}\n"
            "확인 명령: git log --oneline --left-right --graph "
            f"HEAD...{remote_ref}",
            stage="분기된 브랜치 rebase",
            command=exc.command,
            returncode=exc.returncode,
            stdout=exc.stdout,
            stderr=exc.stderr,
        ) from exc


def _safe_relative(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise PublishError(
            f"저장소 내부의 안전한 상대 경로가 아닙니다: {value}",
            stage="발행 경로 검증",
        )
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
    result = {
        "target": name,
        "ok": False,
        "committed": False,
        "pushed": False,
        "stage": "",
        "command": "",
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "message": "",
    }
    stage = "사전 확인"

    if not (repo_path / ".git").exists():
        result["stage"] = stage
        result["message"] = f"{name}: {repo_path}가 Git 저장소가 아닙니다."
        return result
    if not note_path.is_file():
        result["stage"] = stage
        result["message"] = f"{name}: 생성된 MDX 파일을 찾을 수 없습니다: {note_path}"
        return result

    try:
        stage = "작업 트리 상태 확인"
        dirty = _run_git(repo_path, "status", "--porcelain", stage=stage)
        if dirty:
            result["stage"] = stage
            result["message"] = (
                f"{name}: 작업 트리에 미커밋 변경이 있어 발행을 중단했습니다. "
                "대상 저장소의 변경사항을 먼저 커밋하거나 정리해주세요.\n"
                f"변경 파일:\n{dirty}"
            )
            return result

        stage = "원격 저장소 fetch"
        _run_git(repo_path, "fetch", "origin", branch, stage=stage)
        stage = "발행 브랜치 checkout"
        _run_git(repo_path, "checkout", branch, stage=stage)
        stage = "원격 브랜치 동기화"
        _sync_branch(repo_path, branch)

        stage = "게시글 경로 준비"
        posts_dir = _safe_relative(target["posts_dir"])
        if target["category_subdirs"]:
            posts_dir = posts_dir / category
        dest_path = repo_path / posts_dir / note_path.name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        stage = "MDX 파일 복사"
        note_content = note_path.read_text(encoding="utf-8")
        image_url_prefix = target["image_url_prefix"]
        if image_url_prefix != "/blogs":
            note_content = note_content.replace("/blogs/", image_url_prefix + "/")
        dest_path.write_text(note_content, encoding="utf-8", newline="\n")

        en_posts_dir = target.get("en_posts_dir")
        en_note_path = note_path.parent / "en" / note_path.name
        en_dest_path = None
        if en_posts_dir and en_note_path.is_file():
            en_dest_path = repo_path / _safe_relative(en_posts_dir) / note_path.name
            en_dest_path.parent.mkdir(parents=True, exist_ok=True)
            en_content = en_note_path.read_text(encoding="utf-8")
            if image_url_prefix != "/blogs":
                en_content = en_content.replace("/blogs/", image_url_prefix + "/")
            en_dest_path.write_text(en_content, encoding="utf-8", newline="\n")
        elif en_posts_dir:
            print(f"{name}: 영문 MDX가 없어 한국어판만 발행합니다: {en_note_path}")

        stage = "이미지 복사"
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

        staged_paths = [
            dest_path.relative_to(repo_path),
            *[p.relative_to(repo_path) for p in copied_images],
        ]
        if en_dest_path is not None:
            staged_paths.append(en_dest_path.relative_to(repo_path))

        stage = "Git staging"
        _run_git(
            repo_path, "add", "--", *[str(p) for p in staged_paths], stage=stage
        )
        staged = _run_git(
            repo_path, "diff", "--cached", "--name-only", stage="staging 결과 확인"
        )
        if not staged:
            result["ok"] = True
            result["stage"] = "변경사항 확인"
            result["message"] = f"{name}: 변경사항 없음"
            return result

        stage = "Git commit"
        _run_git(
            repo_path, "commit", "-m",
            f"chore(blog): add {content_type} post - {title}",
            stage=stage,
        )
        result["committed"] = True
        if not AUTO_PUSH:
            result["ok"] = True
            result["stage"] = stage
            result["message"] = f"{name}: 로컬 커밋 완료 (AUTO_PUSH=false)"
            return result

        stage = "Git push"
        _run_git(repo_path, "push", "origin", branch, stage=stage)
        result["ok"] = True
        result["pushed"] = True
        result["stage"] = stage
        result["message"] = (
            f"{name}: push 완료 — 배포 자동화가 시작됩니다 "
            f"({dest_path.relative_to(repo_path)})"
        )
        return result

    except (PublishError, OSError, shutil.Error, subprocess.SubprocessError) as exc:
        result["stage"] = getattr(exc, "stage", stage)
        result["command"] = " ".join(getattr(exc, "command", []))
        result["returncode"] = getattr(exc, "returncode", None)
        result["stdout"] = getattr(exc, "stdout", "") or ""
        result["stderr"] = getattr(exc, "stderr", "") or ""
        result["message"] = (
            f"{name}: 발행 실패\n"
            f"단계: {result['stage']}\n"
            f"오류 유형: {type(exc).__name__}\n"
            f"명령: {result['command'] or '(Git 명령 외 작업)'}\n"
            f"종료 코드: {result['returncode'] if result['returncode'] is not None else '(해당 없음)'}\n"
            f"오류 내용: {exc}"
        )
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
