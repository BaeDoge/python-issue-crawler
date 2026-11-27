import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("OMNIROUTE_API_KEY", "unit-test-only")

from topics.translate import _translate_flexible_result, _title_specificity_issue
from publish.git_publish import PublishError, _publish_to_repo, _english_post_destination


class FlexiblePaperTranslationTests(unittest.TestCase):
    def setUp(self):
        self.spec = SimpleNamespace(category_prefix_en="[Paper Review]")
        self.ko = {
            "title": "[논문리뷰] 추론 메모리 최적화",
            "summary": "모델 추론 시 메모리 사용량을 줄이는 방법을 살펴봅니다.",
            "sections": {
                "왜 메모리가 병목이 될까요?": (
                    "가중치와 KV 캐시가 GPU 메모리를 사용합니다.\n\n"
                    "```flow\n모델 가중치 → 추론 → KV 캐시\n```"
                ),
                "양자화는 어떻게 동작할까요?": (
                    "가중치 정밀도를 낮춰 메모리를 절약합니다.\n\n"
                    "```python\nload_model(quantization='4bit')\n```"
                ),
                "어떤 조건에서 주의해야 할까요?": "작업과 모델에 따라 정확도와 지연 시간이 달라질 수 있습니다.",
            },
        }

    def test_translates_dynamic_headings_and_preserves_section_order(self):
        raw = """Title: [Paper Review] Reducing Inference Memory
Summary: A review of techniques for reducing model inference memory.

## [SECTION 1] Why Does Memory Become a Bottleneck?
Weights and the KV cache both consume GPU memory.

```flow
Model weights → inference → KV cache
```

## [SECTION 2] How Does Quantization Work?
Quantization lowers weight precision to reduce memory use.

```python
load_model(quantization='4bit')
```

## [SECTION 3] What Should We Watch For?
Accuracy and latency can vary by task and model.
"""
        translated, issues = _translate_flexible_result(self.spec, self.ko, raw)

        self.assertEqual(issues, [])
        self.assertEqual(
            list(translated["sections"]),
            [
                "Why Does Memory Become a Bottleneck?",
                "How Does Quantization Work?",
                "What Should We Watch For?",
            ],
        )
        self.assertEqual(
            translated["section_map"]["왜 메모리가 병목이 될까요?"],
            "Why Does Memory Become a Bottleneck?",
        )
        self.assertIn("Model weights → inference → KV cache", translated["sections"]["Why Does Memory Become a Bottleneck?"])
        self.assertIn("load_model(quantization='4bit')", translated["sections"]["How Does Quantization Work?"])

    def test_restores_flow_diagram_when_arrow_structure_changes(self):
        from topics.translate import restore_code_blocks

        korean = "내용\n\n```flow\nA → B → C\n```"
        translated = "Text\n\n```flow\nA → B\n```"

        restored = restore_code_blocks(translated, korean)

        self.assertIn("A → B → C", restored)


    def test_restores_original_flow_fence_language(self):
        from topics.translate import restore_code_blocks

        korean = "내용\n\n```flow\nA → B\n```"
        translated = "Text\n\n```text\nA → B\n```"

        restored = restore_code_blocks(translated, korean)

        self.assertIn("```flow", restored)

    def test_preserves_python_code_inside_tilde_fences(self):
        from topics.translate import restore_code_blocks

        korean = "내용\n\n~~~~python\nvalue = 1\n~~~~"
        translated = "Text\n\n~~~~python\nvalue = 1\n~~~~"

        restored = restore_code_blocks(translated, korean)

        self.assertIn("~~~~python", restored)
        self.assertIn("value = 1", restored)

    def test_rejects_generic_placeholder_english_title(self):
        issue = _title_specificity_issue("[Coding Test] Core Keywords", "[Coding Test]")

        self.assertIsNotNone(issue)

    def test_accepts_specific_english_title(self):
        issue = _title_specificity_issue("[Coding Test] Reverse Bits", "[Coding Test]")

        self.assertIsNone(issue)


    def test_rejects_missing_or_reordered_section_markers(self):
        raw = """Title: [Paper Review] Example
Summary: Example summary.

## [SECTION 1] First
English body.

## [SECTION 3] Third
English body.

## [SECTION 2] Second
English body.
"""
        translated, issues = _translate_flexible_result(self.spec, self.ko, raw)

        self.assertIsNone(translated)
        self.assertTrue(any("순서가 바뀜" in issue for issue in issues))

    def test_rejects_korean_left_in_english_prose(self):
        raw = """Title: [Paper Review] Example
Summary: Example summary.

## [SECTION 1] First
English body with 한글.

## [SECTION 2] Second
English body.

## [SECTION 3] Third
English body.
"""
        translated, issues = _translate_flexible_result(self.spec, self.ko, raw)

        self.assertIsNone(translated)
        self.assertTrue(any("한글" in issue for issue in issues))


class BilingualPublishGuardTests(unittest.TestCase):
    def test_english_enabled_target_does_not_publish_korean_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "portfolio"
            (repo / ".git").mkdir(parents=True)
            note = root / "paper.mdx"
            note.write_text("---\ntitle: test\n---\n", encoding="utf-8")

            result = _publish_to_repo(
                target={
                    "name": "portfolio",
                    "repo_path": repo,
                    "branch": "main",
                    "posts_dir": Path("src/app/blog/posts"),
                    "en_posts_dir": Path("src/app/blog/posts/en"),
                    "category_subdirs": False,
                    "images_dir": Path("public/blogs"),
                    "image_url_prefix": "/blogs",
                },
                note_path=note,
                title="test",
                content_type="paper-review",
                image_files=[],
                category="paper",
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["stage"], "영문 MDX 사전 확인")
            self.assertIn("한국어·영어 파일이 모두 준비된 경우", result["message"])


    def test_english_path_mirrors_category_when_category_subdirs_enabled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = _english_post_destination(
                root,
                "content/en",
                "troubleshooting",
                True,
                "example-error.mdx",
            )
            self.assertEqual(
                result,
                root / "content" / "en" / "troubleshooting" / "example-error.mdx",
            )

    def test_english_path_stays_flat_when_category_subdirs_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = _english_post_destination(
                root,
                "src/app/blog/posts/en",
                "paper",
                False,
                "example-paper.mdx",
            )
            self.assertEqual(result, root / "src" / "app" / "blog" / "posts" / "en" / "example-paper.mdx")

    def test_english_path_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(PublishError):
                _english_post_destination(
                    Path(temp),
                    "content/en",
                    "../outside",
                    True,
                    "example.mdx",
                )


if __name__ == "__main__":
    unittest.main()
