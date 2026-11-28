import unittest
from types import SimpleNamespace

from topics.translate import (
    _fixed_translation_issues,
    extract_technical_anchors,
    missing_technical_anchors,
)


class TroubleshootingTranslationConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.spec = SimpleNamespace(
            key="troubleshooting",
            category_prefix_en="[Troubleshooting]",
            section_names=("현상",),
            section_names_en=("Symptom",),
        )

    def test_extracts_inline_commands_versions_errors_and_flags(self):
        tick = chr(96)
        text = (
            "Python 3.11에서 KeyError가 발생합니다. "
            + tick + "python -m pip" + tick + " 명령과 "
            + tick + "setx PATH" + tick + "를 확인하고 "
            + tick + "--user" + tick + " 옵션을 사용합니다."
        )
        anchors = extract_technical_anchors(text)

        self.assertIn("python -m pip", anchors)
        self.assertIn("setx PATH", anchors)
        self.assertIn("--user", anchors)
        self.assertIn("Python 3.11", anchors)
        self.assertIn("KeyError", anchors)

    def test_accepts_english_translation_with_all_technical_anchors(self):
        tick = chr(96)
        ko = {"sections": {"현상": (
            "Python 3.11에서 KeyError가 발생합니다. "
            + tick + "python -m pip" + tick + "와 " + tick + "--user" + tick + "를 확인하세요."
        )}}
        en = {
            "title": "[Troubleshooting] Python KeyError",
            "summary": "A missing dictionary key raises an error.",
            "sections": {
                "Symptom": (
                    "Python 3.11 raises KeyError. Check "
                    + tick + "python -m pip" + tick + " and "
                    + tick + "--user" + tick + "."
                )
            },
        }

        issues = _fixed_translation_issues(self.spec, ko, en)

        self.assertEqual(issues, [])

    def test_rejects_missing_version_or_command_anchor(self):
        tick = chr(96)
        ko = {"sections": {"현상": (
            "Python 3.11에서 KeyError가 발생합니다. "
            + tick + "python -m pip" + tick + "와 " + tick + "--user" + tick + "를 확인하세요."
        )}}
        en = {
            "title": "[Troubleshooting] Python KeyError",
            "summary": "A missing dictionary key raises an error.",
            "sections": {
                "Symptom": (
                    "Python 3.10 raises KeyError. Check "
                    + tick + "pip" + tick + " and " + tick + "--user" + tick + "."
                )
            },
        }

        issues = _fixed_translation_issues(self.spec, ko, en)

        self.assertTrue(any("기술 식별자/버전/명령" in issue for issue in issues))

    def test_anchor_comparison_is_case_insensitive(self):
        missing = missing_technical_anchors(
            "Python 3.11에서 KeyError가 발생합니다.",
            "python 3.11 raises keyerror.",
        )

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
