"""
주제 실행 공통 로직 (구조화 노트 버전)
========================================================================
새 주제를 추가할 때 이 파일을 고칠 필요는 없습니다 — topics/*.py가 TopicSpec을
채워서 run_topic()에 넘기면 됩니다. 공통으로 처리하는 것:

  1. 후보 수집 -> 이미 다룬 소재(history.json)는 제외
  2. Scout가 후보 중 하나를 고른다 (후보의 title을 그대로 반환하게 해서 추적)
  3. 선택된 후보의 상세 자료를 가져온다. 자료가 비어 있으면 다음 후보로 넘어간다
  4. Writer가 '제목:/요약:' + '## 섹션명' 마크다운 형식으로 작성한다(topics/note_format.py가 파싱)
  5. refine_loop으로 검증-재작성 반복 (기계적 검사 + LLM 검수)
  6. output/note.py로 mdx 렌더링, 이력 기록
"""

import json
import re
from difflib import SequenceMatcher
from datetime import datetime
from dataclasses import dataclass, field
from typing import Callable

from crewai import Task, Crew, Process

import history
from config import OUTPUT_DIR, LOG_DIR, QUALITY_ATTEMPTS, PUBLISH_TARGETS
from crew_builder import build_scout_agent, build_writer_agent, build_reviewer_agent
from verify.quality import refine_loop, detect_foreign_language_mixing
from verify.repository_paths import find_unverified_repository_paths as _find_unverified_repository_paths
from topics.note_format import parse_note_text
from output.note import render_note, render_note_en, _FENCE_RE
from topics.translate import translate_note

MAX_CONTEXT_ATTEMPTS = 4   # 상세 자료가 비어 있는 후보를 건너뛰며 시도할 최대 횟수


@dataclass
class TopicSpec:
    key: str
    label: str
    category_prefix: str          # 예: "[트러블슈팅]"
    tag: str                      # frontmatter tag 값
    section_names: list
    gather_candidates: Callable[[], list]
    scout_criteria: str
    writer_role: str
    writer_goal: str
    writer_backstory: str
    reviewer_role: str
    reviewer_goal: str
    reviewer_checklist: str
    # 선택된 후보(dict) -> {"context_text": str, "source_url": str|None,
    #                       "sources": list, "images": list, "third_party": bool}
    build_context: Callable[[dict], dict]
    # Optional English MDX output; translation is skipped unless a publish target configures en_posts_dir.
    category_prefix_en: str = ""
    section_names_en: tuple = ()
    min_section_chars: int = 40
    max_rounds: int = 5
    # 이 섹션에는 "실제 코드"가 담긴 ``` 블록이 있어야 통과 (주석만 있는 블록은 불인정)
    code_required_sections: tuple = ()
    # 주제별 추가 작성 규칙 (Writer 프롬프트 끝에 붙음)
    extra_writer_rules: str = ""
    # {"해결 방법": ("기다려야", ...)} — 해당 섹션에 이 표현이 있으면 재작성
    forbidden_phrases: dict = field(default_factory=dict)
    # Long-form topics can override the default short-note style and require a minimum body size.
    long_form_guidance: str = ""
    min_total_chars: int = 0


def _strip_think(s: str) -> str:
    return re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()


def has_real_code(content: str) -> bool:
    """코드블록 중 주석/빈 줄이 아닌 줄이 하나라도 있는 블록이 있는가.
    ('// 코드 수정 불가' 같은 형식만 맞춘 더미 블록을 걸러내기 위함)"""
    for m in _FENCE_RE.finditer(content or ""):
        inner = m.group(1)
        inner = re.sub(r"^[A-Za-z0-9_+#-]+(?=[ \t]|\r?\n)", "", inner, count=1)
        for line in inner.splitlines():
            s = line.strip()
            if s and not s.startswith(("#", "//", "--", "/*", "*")):
                return True
    return False



def _writer_prompt(spec: TopicSpec, chosen_title: str, context_text: str) -> str:
    sections_desc = "\n".join(f"- {s}" for s in spec.section_names)

    if spec.long_form_guidance:
        mode_instruction = (
            f"'{spec.label}' 장문 분석 블로그를 작성해라. "
            "짧은 요약이나 README 재진술이 아니라, 실제 프로젝트 자료를 근거로 기술적 배경과 동작을 설명해라.\n"
            f"반드시 다음 섹션을 모두 작성할 것:\n{sections_desc}\n\n"
            f"{spec.long_form_guidance}\n\n"
        )
        evidence_rules = (
            "- 저장소의 파일 경로만 확인되고 파일 내용은 제공되지 않았다면, 해당 파일의 내부 구현이나 동작을 안다고 주장하지 말 것\n"
            "- 파일명·함수명·폴더 경로는 참고 자료에 실제로 나온 항목만 언급할 것. 존재 여부가 확인되지 않은 파일명을 만들지 말 것\n"
            "- 프로젝트 고유 사실, 일반적인 도메인 지식, 작성자의 해석을 구분할 것. 해석은 사실처럼 단정하지 말 것\n"
            "- 출처는 실제로 읽은 공식 저장소와 파일에만 연결할 것. 라이선스와 최신 수치는 확인된 자료를 우선할 것\n"
            "- 같은 설명이나 결론을 여러 섹션에서 반복하지 말 것. 분량을 채우기 위한 일반론이나 근거 없는 사회적 효과를 쓰지 말 것\n"
        )
    else:
        mode_instruction = (
            f"'{spec.label}' 노트를 작성해라. 아래 섹션 구조로 정보를 담백하고 명확하게 전달해라"
            f"(각 섹션 2~6문장, 필요하면 코드 블록 포함):\n{sections_desc}\n\n"
        )
        evidence_rules = ""

    shared_rules = (
        "**반드시 지킬 것:**\n"
        "- 참고 자료에 없는 사실을 지어내지 말 것. 참고 자료의 문장을 그대로 복사하지 말고 자기 말로 정리할 것\n"
        "- 코드블록은 ```언어 로 시작해서 ```로 닫고, 여는/닫는 ``` 모두 반드시 새 줄에 쓸 것"
        "(문장 중간에 ```를 붙여 쓰지 말 것)\n"
        "- title은 반드시 '" + spec.category_prefix + " 핵심 키워드' 형식으로, 15~30자 내외, "
        "과장되거나 극적인 표현 없이 담백하게 작성할 것\n"
        "- summary는 1문장으로, 광고 카피처럼 쓰지 말고 무엇을 다루는지만 명확하게 쓸 것\n"
        "- 파일명·함수명·키·명령어는 본문에서 `백틱`으로 감쌀 것\n"
        "- summary에서 원인을 단정하지 말 것. 참고 자료로 확인되지 않은 원인은 본문에서도 "
        "'~로 추정됩니다'로 구분할 것\n"
    )

    return (
        f"소재: {chosen_title}\n\n"
        f"--- 참고 자료 ---\n{context_text}\n--- 끝 ---\n\n"
        + mode_instruction
        + shared_rules
        + evidence_rules
        + (spec.extra_writer_rules + "\n" if spec.extra_writer_rules else "")
        + "\n**출력 형식 (이 형식만 사용하고 앞뒤에 다른 설명을 붙이지 말 것):**\n\n"
        + f"제목: {spec.category_prefix} 핵심 키워드\n"
        + "요약: 한 문장\n\n"
        + "\n\n".join(
            f"## {section}\n(본문 — 코드는 ```언어 ... ``` 블록으로)"
            for section in spec.section_names
        )
        + "\n\n(섹션 헤더는 위와 똑같이 '## 섹션명'으로 쓰고, 모든 섹션을 빠짐없이 쓸 것)"
    )

def _deterministic_check(spec: TopicSpec, repository_paths: list[str] | None = None):
    def check(draft_raw: str) -> dict:
        data = parse_note_text(draft_raw, spec.section_names)
        if not data:
            return {"passed": False, "issues": [
                "형식 파싱 실패 — 첫 줄 '제목: ...', 둘째 줄 '요약: ...' 다음에 '## 섹션명' 헤더로 "
                "각 섹션을 쓰는 형식을 정확히 지킬 것(설명이나 사과문 없이 이 형식만 출력)"
            ]}
        issues = []
        title = data.get("title", "") or ""
        if not title.strip():
            issues.append("title이 비어있음")
        elif not title.startswith(spec.category_prefix):
            issues.append(f"title이 '{spec.category_prefix}'로 시작하지 않음 — 형식을 지킬 것")

        if not (data.get("summary", "") or "").strip():
            issues.append("summary가 비어있음")

        sections = data.get("sections") or {}
        for name in spec.section_names:
            content = (sections.get(name) or "").strip()
            if not content:
                issues.append(f"'{name}' 섹션이 비어있음")
                continue
            if len(content) < spec.min_section_chars:
                issues.append(f"'{name}' 섹션이 너무 짧음(현재 {len(content)}자, 최소 {spec.min_section_chars}자)")
            if content.count("```") % 2 == 1:
                issues.append(f"'{name}' 섹션의 코드블록(```)이 닫히지 않음")
            if name in spec.code_required_sections and not has_real_code(content):
                issues.append(f"'{name}' 섹션에 실제 코드/에러 원문이 담긴 ``` 코드블록이 없음 "
                              "(주석만 있는 블록, 설명만 있는 경우는 인정되지 않음)")
            for phrase in spec.forbidden_phrases.get(name, ()):
                if phrase in content:
                    issues.append(f"'{name}' 섹션에 '{phrase}' 표현이 있음 — 독자가 실제로 따라 할 수 있는 "
                                  "해결 조치를 써야 함(기다리라거나 불가능하다는 내용은 불합격)")

        all_text = title + " " + json.dumps(sections, ensure_ascii=False)
        body_chars = sum(len((sections.get(name) or "").strip()) for name in spec.section_names)
        if spec.min_total_chars and body_chars < spec.min_total_chars:
            issues.append(
                f"본문이 장문 기준보다 짧음(현재 {body_chars}자, 최소 {spec.min_total_chars}자). "
                "배경·기술적 동작 원리·구체적인 활용 사례·한계와 위험을 근거 중심으로 확장할 것"
            )
        if repository_paths:
            all_body_text = "\n".join(
                [title, data.get("summary", "") or ""]
                + [(sections.get(name) or "") for name in spec.section_names]
            )
            unverified_paths = _find_unverified_repository_paths(all_body_text, repository_paths)
            if unverified_paths:
                preview = ", ".join(f"`{path}`" for path in unverified_paths[:5])
                remainder = f" 외 {len(unverified_paths) - 5}개" if len(unverified_paths) > 5 else ""
                issues.append(
                    f"저장소 경로가 실제 Git 트리에서 확인되지 않음: {preview}{remainder}. "
                    "경로를 실제 파일 목록에 맞춰 수정하거나, 확인되지 않는 경로 언급을 삭제할 것"
                )

        issues += detect_foreign_language_mixing(all_text)
        return {"passed": not issues, "issues": issues}
    return check


def _pick_candidate_with_context(spec: TopicSpec, candidates: list, chosen: dict):
    """선택된 후보부터 시작해서, 상세 자료를 못 가져오면 다음 후보로 넘어간다."""
    order = [chosen] + [c for c in candidates if c is not chosen]
    for cand in order[:MAX_CONTEXT_ATTEMPTS]:
        ctx = spec.build_context(cand)
        if ctx.get("context_text"):
            return cand, ctx
        print(f"[{spec.key}] '{cand['title'][:50]}' 상세 자료를 못 가져와서 다음 후보로 넘어갑니다.")
    return None, None


def _normalize_issue(issue: str) -> str:
    """검수 지적의 표현 차이를 줄여 같은 문제인지 비교한다."""
    value = (issue or "").casefold()
    value = re.sub(r"\b(?:현재\s*)?\d+[\d,]*(?:자|개|회|라운드)?\b", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return " ".join(value.split())


def _similar_issue_sets(left: list[str], right: list[str]) -> bool:
    """두 검수 결과의 지적이 대부분 같으면 추가 호출을 생략한다."""
    left_norm = {_normalize_issue(x) for x in left if _normalize_issue(x)}
    right_norm = {_normalize_issue(x) for x in right if _normalize_issue(x)}
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    matched = sum(
        1 for a in left_norm
        if any(SequenceMatcher(None, a, b).ratio() >= 0.84 for b in right_norm)
    )
    return matched / max(len(left_norm), len(right_norm)) >= 0.8


def _quality_issues(result: dict) -> list[str]:
    """최선의 초안에 대응하는 검수 지적을 추출한다."""
    if "final_issues" in result:
        return [str(issue).strip() for issue in (result.get("final_issues") or []) if str(issue).strip()]
    items = result.get("history", []) or []
    if not items:
        return []
    item = items[-1]
    issues = item.get("issues")
    if issues is None:
        issues = (item.get("verdict") or {}).get("issues", [])
    return [str(issue).strip() for issue in (issues or []) if str(issue).strip()]

def _quality_score(result: dict) -> int:
    """통과 결과가 최우선이며, 미통과 결과는 최선의 초안에 대한 지적 수로 비교한다."""
    if result.get("passed"):
        return -1
    if "final_issues" in result:
        return len(result.get("final_issues") or [])
    history_items = result.get("history") or []
    if not history_items:
        return 10_000
    last = history_items[-1]
    issues = last.get("issues")
    if issues is None:
        issues = (last.get("verdict") or {}).get("issues", [])
    return len(issues or [])


def _refine_with_retries(*, writer_agent, critic_agent, initial_prompt: str,
                         critique_instructions: str, expected_output: str,
                         deterministic_check_fn, max_rounds: int, log_prefix: str,
                         stop_on_repeated_issues: bool = False,
                         review_context: str = "") -> dict:
    """검수 사이클을 반복하고, 통과 결과가 없으면 가장 나은 초안을 보존한다.

    장문 주제는 같은 검수 지적이 반복될 때 재작성 루프를 조기에 종료해 토큰과 시간을 낭비하지 않는다.
    짧은 알고리즘/트러블슈팅 주제는 기존 재시도 동작을 유지한다.
    """
    configured_attempts = max(1, QUALITY_ATTEMPTS)
    attempts = min(configured_attempts, 2) if stop_on_repeated_issues else configured_attempts
    best_result = None
    best_score = 10_000
    best_attempt = 1
    all_history = []
    total_rounds = 0
    completed_attempts = 0
    retry_prompt = initial_prompt
    previous_attempt_issues: list[str] = []
    review_error_seen = False

    for attempt in range(1, attempts + 1):
        completed_attempts = attempt
        print(f"{log_prefix}품질 검수 시도 {attempt}/{attempts} (시도당 최대 {max_rounds}라운드)")
        current = refine_loop(
            writer_agent=writer_agent, critic_agent=critic_agent,
            initial_prompt=retry_prompt,
            critique_instructions=critique_instructions,
            expected_output=expected_output,
            deterministic_check_fn=deterministic_check_fn,
            max_rounds=max_rounds,
            log_prefix=f"{log_prefix}[시도 {attempt}/{attempts}] ",
            stop_on_repeated_issues=stop_on_repeated_issues,
            review_context=review_context,
        )
        total_rounds += int(current.get("rounds", 0))
        all_history.extend({"attempt": attempt, **entry} for entry in current.get("history", []))

        if current.get("review_error"):
            review_error_seen = True
            if best_result is None:
                best_result = current
                best_attempt = attempt
            print(f"{log_prefix}검수기 응답 형식 오류로 새 글 생성을 중단합니다. 기존 최선 초안을 보존합니다.")
            break

        score = _quality_score(current)
        if best_result is None or score <= best_score:
            best_result = current
            best_score = score
            best_attempt = attempt

        if current.get("passed"):
            return {**current, "rounds": total_rounds, "attempts": attempt,
                    "best_attempt": attempt, "history": all_history}

        issues = _quality_issues(current)
        if stop_on_repeated_issues and previous_attempt_issues and _similar_issue_sets(previous_attempt_issues, issues):
            print(
                f"{log_prefix}직전 시도와 검수 지적이 사실상 같아 추가 재시도를 중단합니다. "
                "최선의 결과물을 보존합니다."
            )
            break

        previous_attempt_issues = issues
        if attempt < attempts:
            feedback = "\n".join(f"- {issue}" for issue in issues)
            if not feedback:
                feedback = "- 이전 초안이 품질 기준을 통과하지 못한 원인을 구체적으로 다시 점검할 것"
            retry_prompt = (
                f"{initial_prompt}\n\n"
                f"--- 이전 품질 검수 시도 {attempt} 미통과 ---\n"
                "같은 소재를 유지하되 이전 초안을 그대로 반복하지 말고, 아래 지적을 해결한 새 초안을 작성할 것. "
                "이미 충족한 항목은 다시 늘리지 말고, 확인되지 않은 사실을 추가하지 말 것.\n"
                f"{feedback}"
            )
            print(f"{log_prefix}시도 {attempt} 미통과. 지적 사항을 반영해 새 검수 사이클을 시작합니다.")

    assert best_result is not None
    print(
        f"{log_prefix}품질 검수 {completed_attempts}회 시도, 총 {total_rounds}라운드 후에도 미통과. "
        f"{best_attempt}번째 시도의 결과물을 보존합니다."
    )
    return {**best_result, "passed": False, "rounds": total_rounds,
            "attempts": completed_attempts, "best_attempt": best_attempt, "history": all_history,
            "review_error": review_error_seen or bool(best_result.get("review_error"))}

def run_topic(spec: TopicSpec) -> dict:
    candidates = [c for c in spec.gather_candidates() if not history.is_used(spec.key, c.get("link"))]
    if not candidates:
        print(f"⚠️ [{spec.label}] 새로 다룰 후보가 없습니다 (소스 접속 실패이거나 이미 모두 다룬 소재). "
              "네트워크/소스 설정을 확인하거나, 다시 쓰고 싶은 소재는 output_files/history.json에서 지워주세요.")
        return {"ok": False, "reason": "no_candidates"}

    scout = build_scout_agent(judging_criteria=spec.scout_criteria)
    candidates_text = json.dumps(
        [{"title": c["title"], "signal": c.get("signal"), "source": c.get("source"), "meta": c.get("meta")}
         for c in candidates],
        ensure_ascii=False,
    )
    scout_task = Task(
        description=(
            f"{spec.scout_criteria}\n\n후보 목록(JSON):\n{candidates_text}\n\n"
            "가장 적합한 후보 하나를 골라, 그 후보의 title 필드 값을 '정확히 그대로' 출력해라. "
            "다른 설명은 붙이지 말고 title 텍스트만 출력해라."
        ),
        expected_output="후보 목록 중 하나의 title 값 그대로",
        agent=scout,
    )
    Crew(agents=[scout], tasks=[scout_task], process=Process.sequential, verbose=True).kickoff()
    chosen_raw = _strip_think(str(scout_task.output.raw))
    chosen = next((c for c in candidates if c["title"] in chosen_raw or chosen_raw in c["title"]), candidates[0])

    chosen, ctx = _pick_candidate_with_context(spec, candidates, chosen)
    if not chosen:
        print(f"⚠️ [{spec.label}] 어떤 후보도 상세 자료를 가져오지 못했습니다. 소스 접속/스크래핑 설정을 확인해주세요.")
        return {"ok": False, "reason": "no_context"}

    context_text = ctx["context_text"]
    sources = ctx.get("sources") or ([{"platform": spec.label, "title": chosen["title"], "url": ctx["source_url"],
                                       "author": None}] if ctx.get("source_url") else [])
    images = ctx.get("images", [])
    has_third_party = bool(images) or bool(ctx.get("third_party"))

    writer = build_writer_agent(
        role=spec.writer_role, goal=spec.writer_goal, backstory=spec.writer_backstory,
        long_form=bool(spec.long_form_guidance),
    )
    reviewer = build_reviewer_agent(role=spec.reviewer_role, goal=spec.reviewer_goal, checklist=spec.reviewer_checklist)

    prompt = _writer_prompt(spec, chosen["title"], context_text)
    expected = "'제목:'/'요약:' 줄 + '## 섹션명' 헤더로 구성된 마크다운 노트"

    result = _refine_with_retries(
        writer_agent=writer,
        critic_agent=reviewer,
        initial_prompt=prompt,
        critique_instructions=f"아래 '{spec.label}' 초안을 다음 기준으로 평가해라: {spec.reviewer_checklist}",
        expected_output=expected,
        deterministic_check_fn=_deterministic_check(spec, ctx.get("tree_paths")),
        max_rounds=spec.max_rounds,
        log_prefix=f"[{spec.key}] ",
        stop_on_repeated_issues=bool(spec.long_form_guidance),
        review_context=(ctx.get("review_context", "") if spec.long_form_guidance else ""),
    )

    data = parse_note_text(result["raw"], spec.section_names)
    if not result["passed"]:
        log_path = LOG_DIR / f"{spec.key}_{datetime.now():%Y%m%d_%H%M%S}.json"
        log_path.write_text(json.dumps({"chosen": chosen["title"], "history": result["history"],
                                        "final_raw": result["raw"][:4000]}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"[{spec.key}] 라운드별 작성 결과/지적 사항을 저장했습니다: {log_path}")
    if not data or not any(data["sections"].values()):
        print(f"⚠️ [{spec.label}] Writer가 형식에 맞는 글을 끝내 만들지 못해서 파일을 저장하지 않았습니다 "
              "(이 소재는 이력에 기록하지 않아 다음에 다시 시도할 수 있습니다). 위 로그 파일을 확인해주세요.")
        return {"ok": False, "reason": "writer_failed", "chosen": chosen["title"]}

    refine_meta = {
        "review_passed": result["passed"],
        "refine_rounds": result["rounds"],
        "quality_attempts": result.get("attempts", 1),
        "best_quality_attempt": result.get("best_attempt", 1),
        "chosen_candidate": chosen["title"],
        "chosen_link": chosen.get("link"),
    }

    title = data.get("title") or f"{spec.category_prefix} {chosen['title'][:40]}"
    rendered = render_note(
        content_type=spec.key,
        title=title,
        summary=data.get("summary", ""),
        tag=spec.tag,
        sections=data["sections"],
        out_dir=OUTPUT_DIR / spec.key,
        refine_meta=refine_meta,
        sources=sources,
        images=images,
    )

    en_path = None
    wants_english = result["passed"] and any(target.get("en_posts_dir") for target in PUBLISH_TARGETS)
    if wants_english:
        if not spec.category_prefix_en or len(spec.section_names_en) != len(spec.section_names):
            print(f"[{spec.key}] 영문 발행 대상이 있지만 영어 섹션 설정이 없어 번역을 건너뜁니다.")
        else:
            en_data = translate_note(spec, data)
            if en_data:
                en_rendered = render_note_en(
                    ko_result=rendered,
                    title=en_data["title"],
                    summary=en_data["summary"],
                    tag=spec.tag,
                    sections=en_data["sections"],
                    section_map=dict(zip(spec.section_names, spec.section_names_en)),
                    out_dir=OUTPUT_DIR / spec.key,
                )
                en_path = en_rendered["en_path"]
                print(f"영문 MDX 저장됨: {en_path}")
            else:
                print(f"[{spec.key}] 영문 번역 검증에 실패해 영문판만 생략합니다. 한국어 글은 유지됩니다.")

    history.mark_used(spec.key, chosen.get("link"), chosen["title"])

    print(f"\n저장됨: {rendered['path']}")
    if result.get("attempts", 1) > 1:
        review_summary = (
            f"{result['attempts']}회 시도, 총 {result['rounds']}라운드, "
            f"최선의 결과는 {result.get('best_attempt', result['attempts'])}번째 시도"
        )
    else:
        review_summary = f"{result['rounds']}라운드"
    print(f"검토 결과: {review_summary} — "
          f"{'통과' if result['passed'] else '최종 미통과(최선의 결과물로 저장됨 — 수동 검수 권장)'}")
    if rendered["image_files"]:
        print(f"이미지 {len(rendered['image_files'])}장 포함 (mdx 옆 public/blogs/ 에 같이 저장됨).")
    return {
        "ok": True, "passed": result["passed"], "title": title,
        "has_images": bool(rendered["image_files"]), "has_third_party": has_third_party,
        **rendered,
        **({"en_path": en_path} if en_path else {}),
    }
