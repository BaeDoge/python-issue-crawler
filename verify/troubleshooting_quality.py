"""Evidence-linked consistency checks for generated troubleshooting notes.

The hidden manifest ties the source question/answer to the symptom, diagnosis,
and repair sections. It is a deterministic consistency gate, not a substitute
for the LLM reviewer or for executing environment-specific shell commands.
"""

from __future__ import annotations

import json
import re
from typing import Any

from verify.code_blocks import iter_fenced_code_blocks


MANIFEST_MARKER = "TROUBLESHOOTING_CHECKS"
MAX_MANIFEST_CHARS = 16_000
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,79}$")


def _normalize_evidence(value: str) -> str:
    return " ".join((value or "").split()).casefold()


def _extract_manifest_payload(raw: str) -> str | None:
    marker = re.search(
        r"<!--\s*" + re.escape(MANIFEST_MARKER) + r"\b([\s\S]*?)-->",
        raw or "",
        re.IGNORECASE,
    )
    if not marker:
        return None

    all_markers = re.findall(
        r"<!--\s*" + re.escape(MANIFEST_MARKER) + r"\b",
        raw or "",
        re.IGNORECASE,
    )
    if len(all_markers) != 1:
        return None

    first_heading = re.search(r"(?m)^\s{0,3}##\s+", raw or "")
    if first_heading and marker.start() > first_heading.start():
        return None

    body = marker.group(1)
    start = body.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(body)):
        char = body[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return body[start:index + 1]
    return None


def _valid_terms(value: Any, field: str, issues: list[str], *, minimum: int = 1, maximum: int = 3) -> list[str]:
    if (
        not isinstance(value, list)
        or not minimum <= len(value) <= maximum
        or any(not isinstance(item, str) or not _IDENTIFIER_RE.fullmatch(item.strip()) for item in value)
    ):
        issues.append(f"TROUBLESHOOTING_CHECKS: {field}는 영문 식별자/기술 용어 {minimum}~{maximum}개 배열이어야 합니다.")
        return []
    normalized = [item.strip() for item in value]
    if len({item.casefold() for item in normalized}) != len(normalized):
        issues.append(f"TROUBLESHOOTING_CHECKS: {field}에 중복 항목이 있습니다.")
        return []
    return normalized


def _contains_term(text: str, term: str) -> bool:
    source = (text or "").casefold()
    needle = term.casefold()
    if not needle:
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", term):
        return re.search(r"(?<![A-Za-z0-9_])" + re.escape(needle) + r"(?![A-Za-z0-9_])", source) is not None
    return needle in source


def validate_troubleshooting_consistency(
    raw: str,
    sections: dict[str, str],
    *,
    review_context: str = "",
) -> list[str]:
    """Validate source evidence and the traceability of symptom/cause/fix.

    The manifest's references use zero-based indexes across all fenced blocks
    in each named section, regardless of their language.
    """
    payload = _extract_manifest_payload(raw)
    if not payload:
        return [
            "트러블슈팅 근거 명세가 없습니다. 첫 섹션 제목 앞에 TROUBLESHOOTING_CHECKS JSON 주석을 추가할 것."
        ]
    if len(payload) > MAX_MANIFEST_CHARS:
        return ["TROUBLESHOOTING_CHECKS 명세가 너무 큽니다. 필수 근거와 앵커만 남길 것."]
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        return [f"TROUBLESHOOTING_CHECKS JSON 오류({exc.lineno}행): 올바른 JSON으로 수정할 것."]
    if not isinstance(manifest, dict):
        return ["TROUBLESHOOTING_CHECKS는 JSON 객체여야 합니다."]

    issues: list[str] = []
    source_quote = manifest.get("source_quote")
    if not isinstance(source_quote, str) or len(source_quote.strip()) < 24:
        issues.append("TROUBLESHOOTING_CHECKS: source_quote에는 원문에서 복사한 24자 이상의 연속 구절이 필요합니다.")
    elif not review_context or _normalize_evidence(source_quote) not in _normalize_evidence(review_context):
        issues.append("TROUBLESHOOTING_CHECKS: source_quote가 실제 질문/답변/공식 문서 근거에서 확인되지 않습니다.")

    error_signature = manifest.get("error_signature")
    symptom = sections.get("현상", "") or ""
    cause = sections.get("원인", "") or ""
    solution = sections.get("해결 방법", "") or ""
    if not isinstance(error_signature, str) or len(error_signature.strip()) < 3:
        issues.append("TROUBLESHOOTING_CHECKS: error_signature에 구체적인 예외명 또는 오류 메시지를 지정할 것.")
    else:
        if not _contains_term(source_quote if isinstance(source_quote, str) else "", error_signature):
            issues.append("TROUBLESHOOTING_CHECKS: error_signature가 source_quote에 없습니다.")
        if not _contains_term(symptom, error_signature):
            issues.append("현상 섹션에 원문 오류 서명(error_signature)이 없습니다.")

    reproduction_index = manifest.get("reproduction_block_index")
    fix_index = manifest.get("fix_block_index")
    for field, value in (("reproduction_block_index", reproduction_index), ("fix_block_index", fix_index)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            issues.append(f"TROUBLESHOOTING_CHECKS: {field}는 0 이상의 정수여야 합니다.")

    symptom_blocks = list(iter_fenced_code_blocks(symptom))
    solution_blocks = list(iter_fenced_code_blocks(solution))
    reproduction_block = None
    fix_block = None
    if isinstance(reproduction_index, int) and not isinstance(reproduction_index, bool) and reproduction_index >= 0:
        if reproduction_index >= len(symptom_blocks):
            issues.append("TROUBLESHOOTING_CHECKS: 현상 섹션의 reproduction_block_index를 찾을 수 없습니다.")
        elif not symptom_blocks[reproduction_index].complete:
            issues.append("TROUBLESHOOTING_CHECKS: 재현 코드 블록이 닫히지 않았습니다.")
        else:
            reproduction_block = symptom_blocks[reproduction_index]
    if isinstance(fix_index, int) and not isinstance(fix_index, bool) and fix_index >= 0:
        if fix_index >= len(solution_blocks):
            issues.append("TROUBLESHOOTING_CHECKS: 해결 방법 섹션의 fix_block_index를 찾을 수 없습니다.")
        elif not solution_blocks[fix_index].complete:
            issues.append("TROUBLESHOOTING_CHECKS: 해결 코드 블록이 닫히지 않았습니다.")
        else:
            fix_block = solution_blocks[fix_index]

    shared_terms = _valid_terms(manifest.get("shared_terms"), "shared_terms", issues)
    if shared_terms and isinstance(source_quote, str):
        for term in shared_terms:
            if not _contains_term(source_quote, term):
                issues.append(f"TROUBLESHOOTING_CHECKS: shared_terms의 '{term}'가 원문 인용에 없습니다.")
            if reproduction_block and not _contains_term(reproduction_block.body, term):
                issues.append(f"현상 재현 블록에 원문 핵심 식별자 '{term}'가 없습니다.")
            if fix_block and not _contains_term(fix_block.body, term):
                issues.append(f"해결 코드에 원문 핵심 식별자 '{term}'가 없습니다.")

    cause_terms = _valid_terms(manifest.get("cause_terms"), "cause_terms", issues)
    for term in cause_terms:
        if not _contains_term(cause, term):
            issues.append(f"원인 설명에 검증 기준 '{term}'가 없습니다.")

    fix_terms = _valid_terms(manifest.get("fix_terms"), "fix_terms", issues)
    for term in fix_terms:
        if not _contains_term(solution, term):
            issues.append(f"해결 방법에 실제 조치 앵커 '{term}'가 없습니다.")

    environment = manifest.get("environment", {})
    if not isinstance(environment, dict):
        issues.append("TROUBLESHOOTING_CHECKS: environment는 객체여야 합니다.")
    else:
        for package, version in environment.items():
            if not isinstance(package, str) or not isinstance(version, str) or not package.strip() or not version.strip():
                issues.append("TROUBLESHOOTING_CHECKS: environment의 패키지명과 버전은 문자열이어야 합니다.")
                continue
            claim = f"{package} {version}"
            if not _contains_term(source_quote if isinstance(source_quote, str) else "", claim):
                issues.append(f"TROUBLESHOOTING_CHECKS: 버전 주장 '{claim}'이 원문 인용에 없습니다.")
            if not _contains_term(symptom + "\n" + cause + "\n" + solution, claim):
                issues.append(f"본문에서 원문 환경 버전 '{claim}'을 확인할 수 없습니다.")

    marker_count = len(re.findall(r"<!--\s*" + re.escape(MANIFEST_MARKER) + r"\b", raw or "", re.IGNORECASE))
    if marker_count != 1:
        issues.append("TROUBLESHOOTING_CHECKS 명세는 문서 첫 부분에 한 번만 있어야 합니다.")

    return list(dict.fromkeys(issues))
