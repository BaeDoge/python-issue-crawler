import unittest

from verify.code_quality import validate_python_code_blocks
from verify.quality import has_noop_loop_code


class PythonCodeQualityTests(unittest.TestCase):
    def test_detects_top_level_return_syntax_error(self):
        fence = chr(96) * 3
        source = fence + "python\nreturn 3\n" + fence
        issues = validate_python_code_blocks(source)

        self.assertTrue(any("문법 오류" in issue for issue in issues))

    def test_detects_missing_typing_import(self):
        fence = chr(96) * 3
        source = (
            fence + "python\n"
            "class Solution:\n"
            "    def values(self, items: List[int]) -> List[int]:\n"
            "        return items\n"
            + fence
        )
        issues = validate_python_code_blocks(source)

        self.assertTrue(any("List" in issue and "typing" in issue for issue in issues))

    def test_detects_missing_deque_import(self):
        fence = chr(96) * 3
        source = (
            fence + "python\n"
            "def breadth_first(items):\n"
            "    queue = deque(items)\n"
            "    return queue\n"
            + fence
        )
        issues = validate_python_code_blocks(source)

        self.assertTrue(any("deque" in issue and "collections" in issue for issue in issues))

    def test_accepts_imported_typing_and_standard_library_names(self):
        fence = chr(96) * 3
        source = (
            fence + "python\n"
            "from collections import deque\n"
            "from typing import List\n"
            "def breadth_first(items: List[int]) -> List[int]:\n"
            "    return list(deque(items))\n"
            + fence
        )
        self.assertEqual(validate_python_code_blocks(source), [])

    def test_accepts_platform_provided_tree_node_with_forward_reference(self):
        fence = chr(96) * 3
        source = (
            fence + "python\n"
            "from typing import Optional\n"
            "def depth(root: Optional['TreeNode']) -> int:\n"
            "    return 0 if root is None else 1\n"
            + fence
        )
        self.assertEqual(validate_python_code_blocks(source), [])

    def test_detects_pass_only_function_stub(self):
        fence = chr(96) * 3
        source = (
            fence + "python\n"
            "class Solution:\n"
            "    def reverseBits(self, n: int) -> int:\n"
            "        pass\n"
            + fence
        )
        issues = validate_python_code_blocks(source)

        self.assertTrue(any("미완성 함수" in issue for issue in issues))

    def test_detects_ellipsis_only_function_stub(self):
        fence = chr(96) * 3
        source = (
            fence + "python\n"
            "def not_finished(value):\n"
            "    ...\n"
            + fence
        )
        issues = validate_python_code_blocks(source)

        self.assertTrue(any("미완성 함수" in issue for issue in issues))

    def test_detects_tilde_fenced_python_too(self):
        source = "~~~~python\ndef example():\n    pass\n~~~~"
        issues = validate_python_code_blocks(source)

        self.assertTrue(any("미완성 함수" in issue for issue in issues))

    def test_noop_loop_detection_supports_tilde_fences(self):
        source = "~~~python\nfor item in values:\n    pass\n~~~"
        self.assertTrue(has_noop_loop_code(source))


if __name__ == "__main__":
    unittest.main()
