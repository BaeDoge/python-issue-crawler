"""
통합 엔진 — 주제 생성 -> 검증(+영문 번역) -> 발행 대상(Target)에 발행
========================================================================
수동 실행(원할 때마다):
    uv run pipeline/engine.py                       # 메뉴에서 선택
    uv run pipeline/engine.py --topic troubleshooting
    uv run pipeline/engine.py --topic algorithm
    uv run pipeline/engine.py --topic both           # 둘 다 한 편씩
    uv run pipeline/engine.py --topic both --no-publish   # 생성만

발행 상태 보기 / 묶음 push:
    uv run pipeline/engine.py --status               # 대상별 오늘 발행 수, 대기 글, 허가 대기/미통과 수
    uv run pipeline/engine.py --flush                # batch 대상에 쌓인 커밋을 지금 push

보류된 초안 발행(원저작자 허가 확인 후 등):
    uv run pipeline/engine.py --publish-draft output_files/troubleshooting/xxx.mdx --target techblog

접속 문제 점검:
    uv run pipeline/engine.py --diagnose

자동 반복 실행은 scheduler.py (하루 1회 / --continuous 연속 생성).

발행 규칙(대상 설정은 targets.toml 또는 .env — targets.example.toml 참고):
- 검증을 최종 통과하지 못한 글은 어떤 대상에도 자동 발행되지 않습니다.
- 다른 사람의 이미지/블로그 글을 참고한 글은 대상의 hold_third_party=true면 자동 발행되지 않습니다.
- 대상마다 daily_limit까지만 하루에 발행하고, 넘치는 글은 대기열에 남았다가 다음 날 나갑니다.
"""

import argparse
import sys
from pathlib import Path

import pubqueue
from topics import TOPICS, topic_choices
from publish.git_publish import publish_note, publish_eligible, flush_batches, unpushed_count
from targets import load_targets, get_target


def _parse_args():
    parser = argparse.ArgumentParser(description="트러블슈팅/알고리즘 노트를 생성하고 발행 대상에 올립니다")
    parser.add_argument("--topic", choices=[*TOPICS.keys(), "both"], help="생성할 주제 (생략하면 메뉴가 뜸)")
    parser.add_argument("--no-publish", action="store_true", help="생성만 하고 발행은 하지 않음")
    parser.add_argument("--status", action="store_true", help="발행 상태/대기열 요약")
    parser.add_argument("--flush", action="store_true", help="batch 대상에 쌓인 커밋을 지금 push")
    parser.add_argument("--diagnose", action="store_true",
                        help="소스별 접속 상태를 점검하고 실패 원인을 출력 (후보가 안 나올 때 먼저 실행)")
    parser.add_argument("--publish-draft", metavar="MDX_PATH", help="이미 생성된 mdx 초안을 지정한 대상에 발행")
    parser.add_argument("--target", help="--publish-draft 대상 이름 (all이면 모든 대상)")
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


def generate(topic_key: str) -> dict:
    print(f"\n{'=' * 60}\n[{topic_key}] 생성 시작\n{'=' * 60}")
    result = TOPICS[topic_key].run()
    if not result.get("ok"):
        print(f"[{topic_key}] 생성 실패/스킵: {result.get('reason')}")
        return result
    if not result.get("passed"):
        print(f"[{topic_key}] ⚠️ 검증을 최종 통과하지 못한 결과물입니다 — 자동 발행하지 않고 로컬 파일로만 남깁니다.")
        print(f"파일: {result['path']}")
    elif result.get("has_third_party"):
        print(f"[{topic_key}] 다른 사람의 이미지/블로그 글을 참고한 글입니다 — hold_third_party=true인 대상에는 "
              "자동 발행되지 않습니다. 허가를 받으신 뒤:")
        print(f"  uv run pipeline/engine.py --publish-draft \"{result['path']}\" --target 이름")
    return result


def publish_pending() -> list:
    msgs = publish_eligible()
    for m in msgs:
        print(m)
    return msgs


def run_one(topic_key: str, publish: bool = True) -> dict:
    result = generate(topic_key)
    if publish and result.get("ok"):
        if not load_targets():
            print("ℹ️ 발행 대상이 없어 생성까지만 했습니다(.env의 PORTFOLIO_REPO_PATH 또는 targets.toml 설정 필요).")
        else:
            publish_pending()
    return result


def publish_draft(mdx_path: str, target_name: str | None) -> None:
    mdx = Path(mdx_path)
    meta_path = mdx.with_suffix(".meta.json")
    if not mdx.exists() or not meta_path.exists():
        print(f"mdx와 같은 폴더에 .meta.json이 있어야 합니다: {mdx}")
        return
    targets = load_targets()
    if target_name in (None, ""):
        if len(targets) != 1:
            print("대상이 여러 개입니다. --target 이름 (또는 all)을 지정해주세요: " + ", ".join(t.name for t in targets))
            return
        chosen = targets
    elif target_name == "all":
        chosen = targets
    else:
        t = get_target(target_name)
        if not t:
            print(f"알 수 없는 대상: {target_name} (사용 가능: {', '.join(x.name for x in targets)})")
            return
        chosen = [t]
    for t in chosen:
        res = publish_note(meta_path, t)
        print(res["message"])
        if res["committed"]:
            pubqueue.mark_published(meta_path, t.name)
    for m in flush_batches(chosen):
        print(m)


def show_status() -> None:
    targets = load_targets()
    s = pubqueue.summary(targets)
    print(f"생성된 노트 {s['total']}개 — 검증 미통과 {s['review_failed']}개, 허가 대기(타인 자료 참고) {s['third_party']}개")
    if not targets:
        print("발행 대상이 없습니다 (.env의 PORTFOLIO_REPO_PATH 또는 targets.toml 설정 필요).")
    for t in targets:
        limit = t.daily_limit or "무제한"
        extra = f", push 대기 커밋 {unpushed_count(t)}개" if t.mode == "batch" else ""
        print(f"- {t.name}: 오늘 {s['today'][t.name]}/{limit}편 발행, 발행 대기 {s['waiting'][t.name]}편"
              f"{extra} (모드 {t.mode}, 영문 {'O' if t.wants_english else 'X'})")


def main():
    args = _parse_args()

    if args.diagnose:
        from diagnose import run_diagnose
        run_diagnose()
        return
    if args.status:
        show_status()
        return
    if args.flush:
        msgs = flush_batches(force=True)
        print("\n".join(msgs) if msgs else "push할 커밋이 없습니다.")
        return
    if args.publish_draft:
        publish_draft(args.publish_draft, args.target)
        return

    topic_key = args.topic
    if not topic_key:
        if not sys.stdin.isatty():
            print("⚠️ 비대화형 환경에서는 --topic을 지정해주세요 (troubleshooting | algorithm | both)")
            sys.exit(1)
        topic_key = _resolve_via_inquirer()

    if not args.no_publish and not load_targets():
        print("ℹ️ 발행 대상이 없어 이번 실행은 mdx 생성까지만 됩니다 (파일은 output_files/ 에 저장됨).")

    keys = list(TOPICS.keys()) if topic_key == "both" else [topic_key]
    for key in keys:
        run_one(key, publish=not args.no_publish)


if __name__ == "__main__":
    main()
