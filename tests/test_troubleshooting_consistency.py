import json
import unittest

from topics.note_format import parse_note_text
from topics.troubleshooting import SPEC
from topics._common import _deterministic_check
from verify.troubleshooting_quality import validate_troubleshooting_consistency


SOURCE_QUOTE = (
    "In Python 3.11, reading data['username'] raises KeyError when the key is missing."
)
FENCE = chr(96) * 3


def make_draft(*, source_quote=SOURCE_QUOTE, shared_terms=None, cause_terms=None, fix_terms=None,
               error_signature="KeyError", reproduction_block_index=0, fix_block_index=0,
               environment=None, fix_code=None):
    manifest = {
        "source_quote": source_quote,
        "error_signature": error_signature,
        "reproduction_block_index": reproduction_block_index,
        "fix_block_index": fix_block_index,
        "shared_terms": shared_terms if shared_terms is not None else ["data", "username"],
        "cause_terms": cause_terms if cause_terms is not None else ["dictionary", "key"],
        "fix_terms": fix_terms if fix_terms is not None else ["get"],
        "environment": environment if environment is not None else {"Python": "3.11"},
    }
    fix_code = fix_code or "value = data.get('username')"
    symptom = (
        "In Python 3.11, the original operation raises KeyError when the username key is absent.\n\n"
        + FENCE + "python\n"
        + "value = data['username']\n"
        + FENCE
    )
    cause = "A dictionary lookup raises an exception when the requested key is not present."
    solution = (
        "Use get to handle the missing key while keeping the original data variable.\n\n"
        + FENCE + "python\n"
        + fix_code + "\n"
        + FENCE
    )
    sections = {
        "현상": symptom,
        "원인": cause,
        "해결 방법": solution,
        "다른 해결 방법": "Check key membership before indexing when a separate branch is needed.",
        "추가 참고사항": "Choose a default value only when it matches the application's intended behavior.",
    }
    raw = (
        "<!-- TROUBLESHOOTING_CHECKS\n"
        + json.dumps(manifest, ensure_ascii=False)
        + "\n-->\n"
        + "제목: [트러블슈팅] Python KeyError 해결\n"
        + "요약: Python dictionary에서 없는 키를 조회할 때 발생하는 오류와 수정 방법을 정리합니다.\n\n"
        + "## 현상\n" + symptom + "\n\n"
        + "## 원인\n" + cause + "\n\n"
        + "## 해결 방법\n" + solution + "\n\n"
        + "## 다른 해결 방법\n" + sections["다른 해결 방법"] + "\n\n"
        + "## 추가 참고사항\n" + sections["추가 참고사항"]
    )
    context = (
        "StackOverflow question excerpt:\n"
        + SOURCE_QUOTE
        + "\nAccepted answer: Use dict.get when a missing key should return a default."
    )
    return raw, sections, context


class TroubleshootingConsistencyTests(unittest.TestCase):
    def test_accepts_source_linked_symptom_cause_and_fix(self):
        raw, sections, context = make_draft()

        self.assertEqual(
            validate_troubleshooting_consistency(raw, sections, review_context=context),
            [],
        )

    def test_requires_a_source_backed_quote(self):
        raw, sections, context = make_draft(source_quote="This invented explanation is not in source evidence.")
        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("실제 질문/답변/공식 문서 근거" in issue for issue in issues))

    def test_rejects_invented_identifier_in_fix(self):
        raw, sections, context = make_draft(
            shared_terms=["data", "referenceElement"],
            fix_code="value = referenceElement.get('username')",
        )
        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("shared_terms의 'referenceElement'" in issue for issue in issues))
        self.assertTrue(any("현상 재현 블록에 원문 핵심 식별자" in issue for issue in issues))

    def test_rejects_fix_that_does_not_share_source_identifiers(self):
        raw, sections, context = make_draft(fix_code="value = payload.get('username')")
        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("해결 코드에 원문 핵심 식별자 'data'" in issue for issue in issues))

    def test_rejects_error_signature_missing_from_symptom(self):
        raw, sections, context = make_draft(error_signature="IndexError")
        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("현상 섹션에 원문 오류 서명" in issue for issue in issues))

    def test_rejects_cause_term_not_supported_by_source_even_if_written(self):
        raw, sections, context = make_draft(cause_terms=["inventedCause"])
        sections["원인"] += " inventedCause"

        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("원인 근거 'inventedCause'" in issue for issue in issues))

    def test_rejects_fix_term_not_supported_by_source_even_if_in_code(self):
        raw, sections, context = make_draft(
            fix_terms=["inventedFix"],
            fix_code="value = data.inventedFix('username')",
        )

        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("해결 조치 근거 'inventedFix'" in issue for issue in issues))

    def test_rejects_cause_and_fix_anchor_mismatch(self):
        raw, sections, context = make_draft(cause_terms=["attribute"], fix_terms=["setdefault"])
        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("원인 설명에 검증 기준 'attribute'" in issue for issue in issues))
        self.assertTrue(any("해결 방법에 실제 조치 앵커 'setdefault'" in issue for issue in issues))

    def test_version_can_be_evidenced_elsewhere_in_source_context(self):
        raw, sections, context = make_draft(
            source_quote="reading data['username'] raises KeyError when the key is missing."
        )

        self.assertEqual(
            validate_troubleshooting_consistency(raw, sections, review_context=context),
            [],
        )

    def test_rejects_unsupported_version_claim(self):
        raw, sections, context = make_draft(environment={"pandas": "3.0"})
        issues = validate_troubleshooting_consistency(raw, sections, review_context=context)

        self.assertTrue(any("버전 주장 'pandas 3.0'" in issue for issue in issues))

    def test_rejects_manifest_after_first_heading(self):
        raw, sections, context = make_draft()
        start = raw.index("<!-- TROUBLESHOOTING_CHECKS")
        end = raw.index("-->", start) + 3
        manifest = raw[start:end]
        misplaced = raw[:start] + raw[end:]
        misplaced = misplaced.replace("## 현상", "## 현상\n\n" + manifest, 1)

        issues = validate_troubleshooting_consistency(misplaced, sections, review_context=context)

        self.assertTrue(any("TROUBLESHOOTING_CHECKS JSON 주석" in issue for issue in issues))

    def test_note_parser_keeps_hidden_manifest_out_of_public_sections(self):
        raw, _, _ = make_draft()
        parsed = parse_note_text(raw, SPEC.section_names)

        self.assertIsNotNone(parsed)
        self.assertNotIn("TROUBLESHOOTING_CHECKS", "\n".join(parsed["sections"].values()))

    def test_quality_gate_runs_troubleshooting_consistency_check(self):
        raw, _, context = make_draft()
        checker = _deterministic_check(SPEC, review_context=context)
        result = checker(raw)

        self.assertTrue(result["passed"], result["issues"])


if __name__ == "__main__":
    unittest.main()
