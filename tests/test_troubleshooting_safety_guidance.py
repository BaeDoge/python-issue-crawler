import os
import unittest

os.environ.setdefault("OMNIROUTE_API_KEY", "unit-test-only")

from topics.troubleshooting import SPEC


class TroubleshootingSafetyGuidanceTests(unittest.TestCase):
    def test_windows_path_changes_distinguish_temporary_and_persistent_steps(self):
        guidance = " ".join(
            [
                SPEC.reviewer_checklist,
                SPEC.revision_guidance,
                SPEC.extra_writer_rules,
            ]
        )

        self.assertIn("setx PATH", guidance)
        self.assertIn("python -m pip", guidance)
        self.assertIn("영구", guidance)
        self.assertIn("기존", guidance)

    def test_shell_commands_must_be_labeled_and_scoped(self):
        guidance = " ".join(
            [
                SPEC.reviewer_checklist,
                SPEC.revision_guidance,
                SPEC.extra_writer_rules,
            ]
        )

        self.assertIn("PowerShell", guidance)
        self.assertIn("현재 CMD 세션", guidance)
        self.assertIn("되돌리는 방법", guidance)


if __name__ == "__main__":
    unittest.main()
