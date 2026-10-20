"""
검증 - 재작성 반복 루프
========================================================
글 하나를 "초안 작성 -> 기계적 검사 -> LLM 검수 -> (문제 있으면) 재작성"
순서로 max_rounds까지 반복합니다. 기계적 검사(JSON 형식, 필드 누락, 외국어 혼입
등)를 먼저 돌려서 싸고 확실한 문제부터 걸러내고, 통과하면 LLM 검수로 넘어갑니다.
"""

import json
import re

from crewai import Task, Crew, Process

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

# 한국어/영어/코드에 쓰이는 문자(한글, 영문, 숫자, 기본 기호) 밖의 CJK 문자 —
# 중국어/일본어 전용 한자·가나가 섞였는지 체크하는 용도
_FOREIGN_CJK_RE = re.compile(
    r"[\u3040-\u30ff\uff66-\uff9f]"  # 히라가나/가타카나
)


def extract_json(raw: str) -> dict | None:
    """모델이 JSON 앞뒤에 설명을 붙이거나 코드펜스로 감싸는 경우가 많아, 가장 큰
    {...} 블록만 추출해서 파싱한다."""
    # 추론 모델(<think>...</think>)이 JSON 앞에 생각 과정을 붙이는 경우 제거
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        # 가장 흔한 실패 원인: 이스케이프 안 된 큰따옴표. 단순 보정 시도 후 재파싱.
        fixed = m.group(0)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None


def detect_foreign_language_mixing(text: str) -> list[str]:
    if _FOREIGN_CJK_RE.search(text or ""):
        return ["한국어 외 다른 언어 문자(일본어 등)가 섞여 있음 — 전부 한국어로 다시 쓸 것"]
    return []


def refine_loop(
    *, writer_agent, critic_agent, initial_prompt: str,
    critique_instructions: str, expected_output: str,
    deterministic_check_fn, max_rounds: int = 5, log_prefix: str = "",
) -> dict:
    """반환: {"raw": 최종 원본 텍스트, "passed": bool, "rounds": int, "history": [...]}"""
    prompt = initial_prompt
    history = []
    last_raw = ""

    for round_no in range(1, max_rounds + 1):
        write_task = Task(description=prompt, expected_output=expected_output, agent=writer_agent)
        Crew(agents=[writer_agent], tasks=[write_task], process=Process.sequential, verbose=True).kickoff()
        raw = str(write_task.output.raw)
        last_raw = raw

        det = deterministic_check_fn(raw)
        if not det["passed"]:
            issues = det["issues"]
            print(f"{log_prefix}[{round_no}라운드] 기계적 검사 실패: {issues}")
            history.append({"round": round_no, "stage": "deterministic", "issues": issues, "raw_head": raw[:2500]})
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
        print(f"{log_prefix}[{round_no}라운드] 검수 미통과: {issues}")
        prompt = (
            f"{initial_prompt}\n\n"
            f"--- 검수자가 아래 문제를 지적함, 반드시 고쳐서 다시 작성할 것 ---\n"
            + "\n".join(f"- {i}" for i in issues)
        )

    print(f"{log_prefix}최대 라운드({max_rounds}) 도달 — 마지막 결과로 진행")
    return {"raw": last_raw, "passed": False, "rounds": max_rounds, "history": history}
