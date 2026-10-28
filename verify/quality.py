"""
검증 - 재작성 반복 루프
========================================================
글 하나를 "초안 작성 -> 기계적 검사 -> LLM 검수 -> (문제 있으면) 재작성"
순서로 max_rounds까지 반복합니다. 기계적 검사(JSON 형식, 필드 누락, 외국어 혼입
등)를 먼저 돌려서 싸고 확실한 문제부터 걸러내고, 통과하면 LLM 검수로 넘어갑니다.
"""

import json
import re
from difflib import SequenceMatcher

from crewai import Task, Crew, Process

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

# 한국어/영어/코드에 쓰이는 문자(한글, 영문, 숫자, 기본 기호) 밖의 CJK 문자 —
# 중국어/일본어 전용 한자·가나가 섞였는지 체크하는 용도
_FOREIGN_CJK_RE = re.compile(
    r"[\u3040-\u30ff\uff66-\uff9f]"  # 히라가나/가타카나
)


def _repair_unescaped_json_quotes(candidate: str) -> str:
    """JSON 문자열 내부의 미이스케이프 큰따옴표를 제한적으로 보정한다."""
    output: list[str] = []
    stack: list[str] = []
    in_string = False
    string_is_key = False
    i = 0
    while i < len(candidate):
        ch = candidate[i]
        if not in_string:
            if ch == '"':
                previous = next((value for value in reversed(output) if not value.isspace()), "")
                string_is_key = bool(stack and stack[-1] == "{" and previous in {"{", ","})
                in_string = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                expected = "{" if ch == "}" else "["
                if stack and stack[-1] == expected:
                    stack.pop()
            output.append(ch)
            i += 1
            continue
        if ch == "\\":
            output.append(ch)
            if i + 1 < len(candidate):
                output.append(candidate[i + 1])
                i += 2
            else:
                i += 1
            continue
        if ch == '"':
            j = i + 1
            while j < len(candidate) and candidate[j].isspace():
                j += 1
            nxt = candidate[j] if j < len(candidate) else ""
            after_comma = candidate[j + 1:].lstrip() if nxt == "," else ""
            closes = (
                not nxt
                or nxt in "]}"
                or (nxt == "," and (after_comma.startswith('"') or not after_comma))
                or (nxt == ":" and string_is_key)
            )
            if closes:
                in_string = False
                string_is_key = False
                output.append(ch)
            else:
                output.append('\\"')
            i += 1
            continue
        output.append(ch)
        i += 1
    return "".join(output)


def _is_review_verdict(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("passed"), bool)
        and isinstance(value.get("issues"), list)
        and all(isinstance(item, str) for item in value.get("issues", []))
    )


def extract_json(raw: str) -> dict | None:
    """LLM 응답에서 유효한 검수 JSON을 찾는다. 설명 텍스트와 추론 태그를 허용한다."""
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    if not text:
        return None

    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*" + re.escape(fence) + r"$", "", text)

    decoder = json.JSONDecoder()
    starts = [index for index, char in enumerate(text) if char == "{"]

    # 우선 원본 응답 그대로 파싱한다.
    for position in starts:
        try:
            value, _ = decoder.raw_decode(text[position:])
        except json.JSONDecodeError:
            continue
        if _is_review_verdict(value):
            return {"passed": value["passed"], "issues": value["issues"]}

    # 리뷰 문장에 포함된 따옴표 때문에 JSON이 깨졌을 때만 제한적으로 보정한다.
    for position in starts:
        repaired = _repair_unescaped_json_quotes(text[position:])
        try:
            value, _ = decoder.raw_decode(repaired)
        except json.JSONDecodeError:
            continue
        if _is_review_verdict(value):
            return {"passed": value["passed"], "issues": value["issues"]}
    return None

def detect_foreign_language_mixing(text: str) -> list[str]:
    if _FOREIGN_CJK_RE.search(text or ""):
        return ["한국어 외 다른 언어 문자(일본어 등)가 섞여 있음 — 전부 한국어로 다시 쓸 것"]
    return []


def _normalize_issue(issue: str) -> str:
    """검수 지적의 표현 차이를 줄여 같은 문제인지 비교한다."""
    value = (issue or "").casefold()
    value = re.sub(r"\b(?:현재\s*)?\d+[\d,]*(?:자|개|회|라운드)?\b", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return " ".join(value.split())


def _similar_issue_sets(left: list[str], right: list[str]) -> bool:
    """연속 검수 라운드의 지적이 대부분 같으면 재작성을 멈춘다."""
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


def refine_loop(
    *, writer_agent, critic_agent, initial_prompt: str,
    critique_instructions: str, expected_output: str,
    deterministic_check_fn, max_rounds: int = 5, log_prefix: str = "",
    stop_on_repeated_issues: bool = False,
) -> dict:
    """반환: {"raw": 최종 원본 텍스트, "passed": bool, "rounds": int, "history": [...]}"""
    prompt = initial_prompt
    history = []
    last_raw = ""
    previous_issues: list[str] = []
    stopped_early = False
    best_raw = ""
    best_issues: list[str] = []
    best_score = float("inf")

    for round_no in range(1, max_rounds + 1):
        write_task = Task(description=prompt, expected_output=expected_output, agent=writer_agent)
        Crew(agents=[writer_agent], tasks=[write_task], process=Process.sequential, verbose=True).kickoff()
        raw = str(write_task.output.raw)
        last_raw = raw

        det = deterministic_check_fn(raw)
        if not det["passed"]:
            issues = det["issues"]
            if stop_on_repeated_issues:
                draft_score = 1000 + len(issues)
                if draft_score < best_score:
                    best_raw, best_issues, best_score = raw, [str(item) for item in issues], draft_score
            print(f"{log_prefix}[{round_no}라운드] 기계적 검사 실패: {issues}")
            history.append({"round": round_no, "stage": "deterministic", "issues": issues, "raw_head": raw[:2500]})
            if stop_on_repeated_issues and previous_issues and _similar_issue_sets(previous_issues, issues):
                print(f"{log_prefix}[{round_no}라운드] 같은 기계적 오류가 반복되어 추가 재작성을 중단합니다.")
                stopped_early = True
                break
            previous_issues = [str(item) for item in issues]
            prompt = (
                f"{initial_prompt}\n\n"
                f"--- 이전 시도에서 아래 문제가 발견됨, 반드시 고쳐서 다시 작성할 것 ---\n"
                + "\n".join(f"- {i}" for i in issues)
            )
            continue

        critic_task = Task(
            description=(
                f"{critique_instructions}\n\n검토 대상:\n{raw}\n\n"
                '문제가 없으면 정확히 {"passed": true, "issues": []} 만 답하고, '
                '문제가 있으면 {"passed": false, "issues": ["문제1", "문제2"]} 형식으로 '
                "구체적으로 뭘 고쳐야 하는지 답할 것. JSON만 답하고 다른 말은 하지 말 것."
            ),
            expected_output='{"passed": true/false, "issues": [...]}',
            agent=critic_agent,
        )
        Crew(agents=[critic_agent], tasks=[critic_task], process=Process.sequential, verbose=True).kickoff()
        verdict = extract_json(str(critic_task.output.raw)) or {"passed": False, "issues": ["검수 응답 파싱 실패"]}

        history.append({"round": round_no, "stage": "critic", "verdict": verdict, "raw_head": raw[:2500]})
        if verdict.get("passed"):
            print(f"{log_prefix}[{round_no}라운드] 통과")
            return {"raw": raw, "passed": True, "rounds": round_no, "history": history}

        issues = verdict.get("issues", [])
        issue_list = [str(item) for item in issues]
        if stop_on_repeated_issues:
            draft_score = len(issue_list)
            if draft_score < best_score:
                best_raw, best_issues, best_score = raw, issue_list, draft_score
        print(f"{log_prefix}[{round_no}라운드] 검수 미통과: {issues}")
        if stop_on_repeated_issues and previous_issues and _similar_issue_sets(previous_issues, issue_list):
            print(f"{log_prefix}[{round_no}라운드] 검수 지적이 반복되어 추가 재작성을 중단합니다.")
            stopped_early = True
            break
        previous_issues = issue_list
        prompt = (
            f"{initial_prompt}\n\n"
            f"--- 검수자가 아래 문제를 지적함, 반드시 고쳐서 다시 작성할 것 ---\n"
            + "\n".join(f"- {i}" for i in issues)
        )

    if stopped_early:
        print(f"{log_prefix}동일한 지적이 반복되어 조기 종료 — 지적 수가 가장 적은 초안을 보존합니다.")
    elif stop_on_repeated_issues:
        print(f"{log_prefix}최대 라운드({max_rounds}) 도달 — 가장 나은 초안을 보존합니다.")
    else:
        print(f"{log_prefix}최대 라운드({max_rounds}) 도달 — 마지막 결과로 진행")
    result = {
        "raw": (best_raw or last_raw) if stop_on_repeated_issues else last_raw,
        "passed": False,
        "rounds": len(history),
        "history": history,
    }
    if stop_on_repeated_issues:
        result["final_issues"] = best_issues
    return result
