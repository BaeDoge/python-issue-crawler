"""
통합 엔진 — 주제 생성 -> 검증 -> 포트폴리오 레포에 발행
========================================================================
수동 실행(원할 때마다):
    uv run pipeline/engine.py                       # 메뉴에서 선택
    uv run pipeline/engine.py --topic troubleshooting
    uv run pipeline/engine.py --topic algorithm
    uv run pipeline/engine.py --topic both           # 둘 다 한 편씩

후보가 안 나오거나 생성이 실패할 때(접속 문제 점검):
    uv run pipeline/engine.py --diagnose

보류된 초안 발행(원저작자 허가 확인 후):
    uv run pipeline/engine.py --publish-draft output_files/troubleshooting/xxx.mdx

자동 반복 실행(하루 1회)은 scheduler.py를 쓰세요:
    uv run pipeline/scheduler.py

발행 규칙:
- 검증을 최종 통과하지 못한 글은 자동 발행하지 않고 로컬에만 남깁니다.
- 다른 사람의 이미지(스크린샷)나 블로그 글을 참고한 글은 AUTO_PUSH 설정과 무관하게
  자동 발행하지 않고 로컬에만 남깁니다(HOLD_THIRD_PARTY=true일 때) — 원저작자 허가를 받은
  뒤 --publish-draft로 직접 발행해주세요.
- --no-publish를 붙이면 어떤 경우든 발행하지 않습니다.
"""

import argparse
import json
import sys
from pathlib import Path

from config import HOLD_THIRD_PARTY, PORTFOLIO_REPO_PATH
from topics import TOPICS, topic_choices
from publish.git_publish import publish_note


def _parse_args():
    parser = argparse.ArgumentParser(description="트러블슈팅/알고리즘 노트를 생성하고 포트폴리오에 발행합니다")
    parser.add_argument("--topic", choices=[*TOPICS.keys(), "both"], help="생성할 주제 (생략하면 메뉴가 뜸)")
    parser.add_argument("--no-publish", action="store_true", help="생성만 하고 포트폴리오 레포엔 올리지 않음")
    parser.add_argument("--diagnose", action="store_true",
                        help="소스별 접속 상태를 점검하고 실패 원인을 출력 (후보가 안 나올 때 먼저 실행)")
    parser.add_argument("--publish-draft", metavar="MDX_PATH",
                        help="이미 생성된(보류 중인) mdx 초안을 포트폴리오 레포에 발행")
    return parser.parse_args()


def _resolve_via_inquirer() -> str:
    import inquirer
    choice = inquirer.list_input(
        "어떤 걸 생성할까요?",
        choices=[f"{label} ({key})" for key, label in topic_choices()] + ["둘 다 (both)"],
    )
    if choice.startswith("둘 다"):
        return "both"
    return choice.split("(")[-1].rstrip(")")


def run_one(topic_key: str, publish: bool) -> dict:
    print(f"\n{'=' * 60}\n[{topic_key}] 생성 시작\n{'=' * 60}")
    result = TOPICS[topic_key].run()
    if not result.get("ok"):
        print(f"[{topic_key}] 생성 실패/스킵: {result.get('reason')}")
        return result

    if not publish:
        print(f"[{topic_key}] --no-publish 옵션으로 발행은 건너뜀. 파일: {result['path']}")
        return result

    if not result.get("passed"):
        print(f"[{topic_key}] ⚠️ 검증을 최종 통과하지 못한 결과물입니다. "
              "자동 발행을 건너뛰고 로컬 파일만 남깁니다 — 직접 검토 후 수동으로 올려주세요.")
        print(f"파일: {result['path']}")
        return result

    if HOLD_THIRD_PARTY and result.get("has_third_party"):
        print(f"[{topic_key}] 다른 사람의 이미지/블로그 글을 참고한 글이라 자동 발행을 보류합니다. "
              "원저작자 허가를 받으신 뒤 아래 명령으로 발행해주세요:")
        print(f"  uv run pipeline/engine.py --publish-draft \"{result['path']}\"")
        result["held_for_permission"] = True
        return result

    pub = publish_note(result["path"], title=result.get("title", ""), content_type=topic_key,
                       image_files=result.get("image_files"))
    print(f"[{topic_key}] 발행 결과: {pub['message']}")
    result["publish"] = pub
    return result


def publish_draft(mdx_path: str) -> dict:
    """보류 중이던 초안을 발행한다. 같은 폴더의 .meta.json에서 제목/타입/이미지
    목록을 읽어온다."""
    path = Path(mdx_path)
    meta_path = path.with_suffix(".meta.json")
    if not path.exists():
        print(f"파일을 찾을 수 없습니다: {path}")
        return {"ok": False}
    if not meta_path.exists():
        print(f"메타 파일이 없습니다: {meta_path} (같은 폴더에 있어야 합니다)")
        return {"ok": False}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    pub = publish_note(path, title=meta.get("title", ""), content_type=meta.get("content_type", "note"),
                       image_files=meta.get("image_files", []))
    print(f"발행 결과: {pub['message']}")
    return pub


def main():
    args = _parse_args()

    if args.diagnose:
        from diagnose import run_diagnose
        run_diagnose()
        return

    if args.publish_draft:
        publish_draft(args.publish_draft)
        return

    topic_key = args.topic
    if not topic_key:
        if not sys.stdin.isatty():
            print("⚠️ 비대화형 환경에서는 --topic을 지정해주세요 (troubleshooting | algorithm | both)")
            sys.exit(1)
        topic_key = _resolve_via_inquirer()

    if not args.no_publish and PORTFOLIO_REPO_PATH is None:
        print("ℹ️ .env에 PORTFOLIO_REPO_PATH가 없어서 이번 실행은 발행 단계 없이 mdx 생성까지만 됩니다 "
              "(파일은 output_files/ 에 저장됨).")

    keys = list(TOPICS.keys()) if topic_key == "both" else [topic_key]
    for key in keys:
        run_one(key, publish=not args.no_publish)


if __name__ == "__main__":
    main()
