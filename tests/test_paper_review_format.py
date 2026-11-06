import unittest

from topics.note_format import parse_note_text


class FlexiblePaperNoteFormatTests(unittest.TestCase):
    def test_dynamic_sections_accept_paper_specific_headings(self):
        raw = """제목: [논문리뷰] KV 캐시 압축
요약: 긴 문맥 추론에서 KV 캐시 메모리를 줄이는 연구를 정리합니다.

## 왜 메모리 사용량이 문제가 될까
긴 문맥은 추론 중 메모리 사용량을 빠르게 늘립니다.

## 제안 방식은 어떻게 동작할까
입력 토큰을 바탕으로 중요한 정보를 보존합니다.

### 구현에서 살펴볼 부분
이 소제목은 앞 섹션 안에 남아 있어야 합니다.

## 실험에서 확인한 점
저자들이 보고한 결과를 원문 범위에서 요약합니다.
"""
        parsed = parse_note_text(raw, ["개발 문제"], allow_dynamic_sections=True)

        self.assertIsNotNone(parsed)
        self.assertEqual(
            list(parsed["sections"]),
            ["왜 메모리 사용량이 문제가 될까", "제안 방식은 어떻게 동작할까", "실험에서 확인한 점"],
        )
        self.assertIn("### 구현에서 살펴볼 부분", parsed["sections"]["제안 방식은 어떻게 동작할까"])

    def test_dynamic_parser_omits_source_heading(self):
        raw = """제목: [논문리뷰] 모델 추론 최적화
요약: 추론 처리량과 메모리 사용량을 함께 다루는 연구입니다.

## 해결하려는 문제
메모리 병목을 줄이는 것이 목표입니다.

## 핵심 아이디어
작은 단계로 최적화를 적용합니다.

## 출처
- 논문 원문: https://example.org/paper
"""
        parsed = parse_note_text(raw, [], allow_dynamic_sections=True)

        self.assertEqual(
            list(parsed["sections"]),
            ["해결하려는 문제", "핵심 아이디어"],
        )

    def test_default_parser_keeps_fixed_heading_behavior(self):
        raw = """제목: [트러블슈팅] 예시
요약: 예시 요약입니다.

## 작성자가 고른 제목
이 섹션은 고정 목차에 없습니다.

## 현상
실제 고정 섹션입니다.
"""
        parsed = parse_note_text(raw, ["현상"])

        self.assertEqual(list(parsed["sections"]), ["현상"])


if __name__ == "__main__":
    unittest.main()
