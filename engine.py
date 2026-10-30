"""
통합 엔진 — 주제 생성 -> 검증 -> 포트폴리오 레포에 발행
========================================================================
수동 실행(원할 때마다):
    uv run pipeline/engine.py                       # 메뉴에서 선택
    uv run pipeline/engine.py --topic troubleshooting
    uv run pipeline/engine.py --topic algorithm
    uv run pipeline/engine.py --topic both           # 둘 다 한 편씩
    uv run pipeline/engine.py --topic algorithm --count 3  # 알고리즘 3편 생성
    uv run pipeline/engine.py --topic both --count 2      # 각 주제 2편씩, 총 4편

후보가 안 나오거나 생성이 실패할 때(접속 문제 점검):
    uv run pipeline/engine.py --diagnose

보류된 초안 발행(원저작자 허가 확인 후):
    uv run pipeline/engine.py --publish-draft output_files/troubleshooting/xxx.mdx

자동 반복 실행(하루 1회)은 scheduler.py를 쓰세요:

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

from config import HOLD_THIRD_PARTY, PUBLISH_TARGETS
from topics import TOPICS, topic_choices
from publish.git_publish import publish_note


def _parse_args():
    parser = argparse.ArgumentParser(description="트러블슈팅/알고리즘 노트를 생성하고 설정된 저장소에 발행합니다")
    parser.add_argument("--topic", choices=[*TOPICS.keys(), "both"], help="생성할 주제 (생략하면 메뉴가 뜸)")
    parser.add_argument("--discover-opensource", action="store_true", help="GitHub 인기/최근 활동 후보만 탐색하고 목록을 출력 (글 생성/발행 안 함)")
    parser.add_argument("--count", type=int, default=1,
                        help="주제별 생성 편수 (기본값: 1, --topic both이면 각 주제에 적용)")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="한 편 생성에 실패하면 남은 반복을 중단")
    parser.add_argument("--no-publish", action="store_true", help="생성만 하고 발행 대상 저장소에는 올리지 않음")
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
    print(f"[{topic_key}] 발행 결과:\n{pub['message']}")
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
    print(f"발행 결과:\n{pub['message']}")
    return pub


def main():
    args = _parse_args()

    if args.diagnose:
        from diagnose import run_diagnose
        run_diagnose()
        return

    if args.discover_opensource:
        from sources.github_trending import discover_github_candidates, print_candidates
        payload = discover_github_candidates()
        print_candidates(payload)
        return

    if args.publish_draft:
        publish_draft(args.publish_draft)
        return

    if args.count < 1:
        raise SystemExit("--count는 1 이상의 정수여야 합니다.")

    topic_key = args.topic
    if not topic_key:
        if not sys.stdin.isatty():
            print("⚠️ 비대화형 환경에서는 --topic을 지정해주세요 (troubleshooting | algorithm | both)")
            sys.exit(1)
        topic_key = _resolve_via_inquirer()

    if not args.no_publish and not PUBLISH_TARGETS:
        print("ℹ️ .env에 PUBLISH_TARGETS가 없어 발행은 건너뜁니다 (파일은 output_files/ 에 저장됨).")

    keys = list(TOPICS.keys()) if topic_key == "both" else [topic_key]
    summary = []
    total_runs = len(keys) * args.count

    print(f"\n생성 계획: {', '.join(keys)} / 주제별 {args.count}편 / 총 {total_runs}회")
    for key in keys:
        for index in range(1, args.count + 1):
            print(f"\n[{key}] {index}/{args.count}편 시작")
            try:
                result = run_one(key, publish=not args.no_publish)
            except KeyboardInterrupt:
                print("\n사용자 요청으로 중단했습니다.")
                raise
            except Exception as exc:
                result = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
                print(f"[{key}] 예외로 실패: {result['reason']}")

            generated = bool(result.get("ok"))
            review_passed = bool(result.get("passed")) if generated else False
            publish_result = result.get("publish") or {}
            publish_attempted = "publish" in result
            publish_ok = bool(publish_result.get("ok")) if publish_attempted else False
            held = bool(result.get("held_for_permission"))
            success = generated and review_passed and not held and (args.no_publish or publish_ok)
            summary.append({
                "topic": key,
                "index": index,
                "ok": success,
                "generated": generated,
                "review_passed": review_passed,
                "publish_attempted": publish_attempted,
                "publish_ok": publish_ok,
                "title": result.get("title", ""),
                "path": str(result.get("path", "")),
                "reason": result.get("reason", ""),
                "publish_message": publish_result.get("message", ""),
                "publish_targets": publish_result.get("targets", []),
                "held": held,
            })

            if not success and args.stop_on_error:
                print("--stop-on-error 옵션에 따라 남은 생성 작업을 중단합니다.")
                break
        if args.stop_on_error and summary and not summary[-1]["ok"]:
            break

    succeeded = sum(1 for item in summary if item["ok"])
    generated_count = sum(1 for item in summary if item["generated"])
    review_passed_count = sum(1 for item in summary if item["review_passed"])
    publish_success_count = sum(1 for item in summary if item["publish_attempted"] and item["publish_ok"])
    held_count = sum(1 for item in summary if item["held"])
    failed = len(summary) - succeeded
    print("\n" + "=" * 60)
    print(f"작업 성공(검수 통과 및 요청된 발행 단계 완료): {succeeded}/{len(summary)}")
    print(f"MDX 생성: {generated_count}/{len(summary)}")
    print(f"검수 통과: {review_passed_count}/{generated_count if generated_count else 0}")
    if not args.no_publish:
        print(f"발행 단계 성공: {publish_success_count}회")
    print(f"검수/발행 보류: {held_count}회")
    print(f"실패 또는 미통과: {failed}회")
    for item in summary:
        if item["held"]:
            status = "초안 보류(제3자 자료 확인 필요)"
        elif not item["generated"]:
            status = "생성 실패"
        elif not item["review_passed"]:
            status = "검수 미통과(파일 저장, 자동 발행 안 함)"
        elif item["publish_attempted"] and not item["publish_ok"]:
            status = "발행 실패"
        elif args.no_publish:
            status = "생성/검수 완료(발행 생략)"
        else:
            status = "성공"

        print(f"- [{item['topic']}] {item['index']}/{args.count}: {status}")
        if item["publish_attempted"] and not item["publish_ok"]:
            # Do not hide the actual error behind the article title.
            print(item["publish_message"] or "발행 실패: 상세 메시지가 반환되지 않았습니다.")
        else:
            detail = item["title"] or item["reason"] or item["path"]
            if detail:
                print(f"  상세: {detail}")
    print("=" * 60)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
