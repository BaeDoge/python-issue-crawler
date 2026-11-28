import json
import unittest

from topics.note_format import parse_note_text
from verify.algorithm_runtime import (
    _validate_solution_source,
    parse_algorithm_test_manifest,
    validate_and_run_algorithm_tests,
)


def _draft(section: str, source: str, entrypoint: str, cases: list[dict]) -> tuple[str, dict[str, str]]:
    manifest = {
        "solutions": [{
            "section": section,
            "block_index": 0,
            "entrypoint": entrypoint,
            "cases": cases,
        }]
    }
    raw = (
        "<!-- ALGORITHM_TESTS\n"
        + json.dumps(manifest, ensure_ascii=False)
        + "\n-->\n"
        + "제목: [코딩테스트] 테스트\n"
        + "요약: 실행 테스트\n"
        + "## 풀이\n"
        + "~~~python\n"
        + source
        + "\n~~~\n"
    )
    return raw, {"풀이": "~~~python\n" + source + "\n~~~"}


class AlgorithmRuntimeTests(unittest.TestCase):
    def test_parses_nested_json_objects_in_hidden_manifest(self):
        cases = [
            {
                "args": [{"values": [1, 2], "nested": {"key": "a } b"}}],
                "expected": {"ok": True},
                "source_example": True,
            },
            {"args": [[], 0], "expected": [], "comparison": "exact"},
            {"args": [[1], 1], "expected": [1]},
        ]
        raw, sections = _draft("풀이", "def solve(value):\n    return value", "solve", cases)

        specs, issues = parse_algorithm_test_manifest(raw, sections)

        self.assertEqual(issues, [])
        self.assertEqual(len(specs), 1)
        self.assertEqual(len(specs[0].cases), 3)

    def test_rejects_manifest_after_first_section_heading(self):
        cases = [
            {"args": [1], "expected": 1, "source_example": True},
            {"args": [2], "expected": 2},
            {"args": [3], "expected": 3},
        ]
        raw, sections = _draft("풀이", "def solve(value):\\n    return value", "solve", cases)
        marker_start = raw.index("<!-- ALGORITHM_TESTS")
        marker_end = raw.index("-->", marker_start) + 3
        manifest = raw[marker_start:marker_end]
        without_manifest = raw[:marker_start] + raw[marker_end:]
        misplaced = without_manifest.replace("## 풀이", "## 풀이\\n" + manifest, 1)

        specs, issues = parse_algorithm_test_manifest(misplaced, sections)

        self.assertEqual(specs, [])
        self.assertTrue(any("ALGORITHM_TESTS" in issue for issue in issues))

    def test_requires_at_least_one_official_example_case(self):
        cases = [
            {"args": [1], "expected": 1},
            {"args": [2], "expected": 2},
            {"args": [3], "expected": 3},
        ]
        raw, sections = _draft("풀이", "def solve(value):\n    return value", "solve", cases)

        _, issues = parse_algorithm_test_manifest(raw, sections)

        self.assertTrue(any("source_example=true" in issue for issue in issues))

    def test_runs_class_method_against_exact_and_unordered_cases(self):
        source = (
            "class Solution:\n"
            "    def twoSum(self, nums, target):\n"
            "        seen = {}\n"
            "        for i, value in enumerate(nums):\n"
            "            if target - value in seen:\n"
            "                return [seen[target - value], i]\n"
            "            seen[value] = i\n"
        )
        cases = [
            {"args": [[2, 7, 11, 15], 9], "expected": [0, 1], "comparison": "unordered_list", "source_example": True},
            {"args": [[3, 2, 4], 6], "expected": [1, 2], "comparison": "unordered_list"},
            {"args": [[3, 3], 6], "expected": [0, 1], "comparison": "unordered_list"},
        ]
        raw, sections = _draft("풀이", source, "Solution.twoSum", cases)

        issues = validate_and_run_algorithm_tests(raw, sections)

        self.assertEqual(issues, [])

    def test_hidden_manifest_is_not_rendered_as_a_note_section(self):
        cases = [
            {"args": [1], "expected": 1, "source_example": True},
            {"args": [2], "expected": 2},
            {"args": [3], "expected": 3},
        ]
        raw, _ = _draft("풀이", "def solve(value):\\n    return value", "solve", cases)

        parsed = parse_note_text(raw, ["풀이"])

        self.assertIsNotNone(parsed)
        self.assertNotIn("ALGORITHM_TESTS", parsed["sections"]["풀이"])
        self.assertNotIn("solutions", parsed["sections"]["풀이"])

    def test_runs_list_node_inputs_and_outputs(self):
        source = (
            "class Solution:\\n"
            "    def middleNode(self, head):\\n"
            "        slow = fast = head\\n"
            "        while fast and fast.next:\\n"
            "            slow = slow.next\\n"
            "            fast = fast.next.next\\n"
            "        return slow\\n"
        )
        cases = [
            {"args": [{"__type__": "ListNode", "values": [1, 2, 3, 4, 5]}], "expected": [3, 4, 5], "source_example": True},
            {"args": [{"__type__": "ListNode", "values": [1, 2]}], "expected": [2]},
            {"args": [{"__type__": "ListNode", "values": [9]}], "expected": [9]},
        ]
        raw, sections = _draft("풀이", source, "Solution.middleNode", cases)

        self.assertEqual(validate_and_run_algorithm_tests(raw, sections), [])

    def test_runs_tree_node_inputs(self):
        source = (
            "from typing import Optional\n"
            "class Solution:\n"
            "    def maxDepth(self, root: Optional[TreeNode]) -> int:\n"
            "        if root is None:\n"
            "            return 0\n"
            "        return 1 + max(self.maxDepth(root.left), self.maxDepth(root.right))\n"
        )
        cases = [
            {"args": [{"__type__": "TreeNode", "level_order": [3, 9, 20, None, None, 15, 7]}], "expected": 3, "source_example": True},
            {"args": [{"__type__": "TreeNode", "level_order": [1]}], "expected": 1},
            {"args": [{"__type__": "TreeNode", "level_order": []}], "expected": 0},
        ]
        raw, sections = _draft("풀이", source, "Solution.maxDepth", cases)

        self.assertEqual(validate_and_run_algorithm_tests(raw, sections), [])

    def test_checks_in_place_mutations(self):
        source = (
            "class Solution:\n"
            "    def moveZeroes(self, nums):\n"
            "        write = 0\n"
            "        for value in nums:\n"
            "            if value != 0:\n"
            "                nums[write] = value\n"
            "                write += 1\n"
            "        for index in range(write, len(nums)):\n"
            "            nums[index] = 0\n"
        )
        cases = [
            {"args": [[0, 1, 0, 3, 12]], "expected": None, "expected_args": [[1, 3, 12, 0, 0]], "source_example": True},
            {"args": [[0]], "expected": None, "expected_args": [[0]]},
            {"args": [[1, 2, 3]], "expected": None, "expected_args": [[1, 2, 3]]},
        ]
        raw, sections = _draft("풀이", source, "Solution.moveZeroes", cases)

        self.assertEqual(validate_and_run_algorithm_tests(raw, sections), [])

    def test_runs_alternative_solution_when_python_code_is_present(self):
        primary = "def solve(value):\\n    return value * 2"
        alternative = "def solve_alt(value):\\n    return sum([value, value])"
        cases_primary = [
            {"args": [2], "expected": 4, "source_example": True},
            {"args": [0], "expected": 0},
            {"args": [-3], "expected": -6},
        ]
        cases_alternative = [
            {"args": [2], "expected": 4, "source_example": True},
            {"args": [0], "expected": 0},
            {"args": [-3], "expected": -6},
        ]
        manifest = {
            "solutions": [
                {"section": "풀이", "block_index": 0, "entrypoint": "solve", "cases": cases_primary},
                {"section": "다른 풀이 방법", "block_index": 0, "entrypoint": "solve_alt", "cases": cases_alternative},
            ]
        }
        raw = (
            "<!-- ALGORITHM_TESTS\\n"
            + json.dumps(manifest, ensure_ascii=False)
            + "\\n-->\\n"
            + "제목: [코딩테스트] 테스트\\n"
            + "요약: 실행 테스트\\n"
            + "## 풀이\\n~~~python\\n" + primary + "\\n~~~\\n"
            + "## 다른 풀이 방법\\n~~~python\\n" + alternative + "\\n~~~\\n"
        )
        sections = {
            "풀이": "~~~python\\n" + primary + "\\n~~~",
            "다른 풀이 방법": "~~~python\\n" + alternative + "\\n~~~",
        }

        self.assertEqual(validate_and_run_algorithm_tests(raw, sections), [])

    def test_fails_when_output_does_not_match_expected_value(self):
        source = "def solve(value):\n    return value + 1"
        cases = [
            {"args": [1], "expected": 1, "source_example": True},
            {"args": [2], "expected": 3},
            {"args": [3], "expected": 4},
        ]
        raw, sections = _draft("풀이", source, "solve", cases)

        issues = validate_and_run_algorithm_tests(raw, sections)

        self.assertTrue(any("결과 불일치" in issue for issue in issues))

    def test_rejects_disallowed_imports_before_execution(self):
        source = "import os\n\ndef solve(value):\n    return value"
        issues = _validate_solution_source(source)

        self.assertTrue(any("허용하지 않는 import" in issue for issue in issues))

    def test_requires_a_manifest(self):
        issues = validate_and_run_algorithm_tests("제목: no manifest", {"풀이": "~~~python\npass\n~~~"})

        self.assertTrue(any("ALGORITHM_TESTS" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
