"""Shared Markdown fenced-code parsing helpers.

Supports both backtick and tilde fences (three or more markers), including
longer opening fences and closing fences that are at least as long.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterator


_BACKTICK = chr(96)
_OPEN_RE = re.compile(r"^ {0,3}(\x60{3,}|~{3,})(.*)$")
_CLOSE_RE = re.compile(r"^ {0,3}(\x60+|~+)[ \t]*$")


@dataclass(frozen=True)
class FencedCodeBlock:
    marker: str
    info: str
    body: str
    raw: str
    start: int
    end: int
    complete: bool

    @property
    def language(self) -> str:
        value = self.info.strip()
        return value.split(None, 1)[0].lower() if value else ""


def iter_fenced_code_blocks(text: str) -> Iterator[FencedCodeBlock]:
    """Yield fenced blocks with source offsets. Unclosed fences are yielded as incomplete."""
    source = text or ""
    lines = source.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    index = 0
    while index < len(lines):
        line = lines[index]
        opening = _OPEN_RE.match(line.rstrip("\r\n"))
        if not opening:
            index += 1
            continue

        marker = opening.group(1)
        info = opening.group(2).strip()
        # CommonMark forbids backticks in the info string of a backtick fence.
        if marker[0] == _BACKTICK and _BACKTICK in info:
            index += 1
            continue

        start = offsets[index]
        body_start = start + len(line)
        closing_index = None
        for candidate_index in range(index + 1, len(lines)):
            candidate = lines[candidate_index].rstrip("\r\n")
            closing = _CLOSE_RE.match(candidate)
            if (
                closing
                and closing.group(1)[0] == marker[0]
                and len(closing.group(1)) >= len(marker)
            ):
                closing_index = candidate_index
                break

        if closing_index is None:
            end = len(source)
            yield FencedCodeBlock(
                marker=marker,
                info=info,
                body=source[body_start:end],
                raw=source[start:end],
                start=start,
                end=end,
                complete=False,
            )
            return

        close_start = offsets[closing_index]
        end = close_start + len(lines[closing_index])
        yield FencedCodeBlock(
            marker=marker,
            info=info,
            body=source[body_start:close_start],
            raw=source[start:end],
            start=start,
            end=end,
            complete=True,
        )
        index = closing_index + 1


def replace_fenced_code_blocks(
    text: str,
    transform: Callable[[FencedCodeBlock], str],
) -> str:
    """Replace each complete or incomplete fenced block without touching surrounding text."""
    source = text or ""
    blocks = list(iter_fenced_code_blocks(source))
    if not blocks:
        return source

    output: list[str] = []
    cursor = 0
    for block in blocks:
        output.append(source[cursor:block.start])
        output.append(transform(block))
        cursor = block.end
    output.append(source[cursor:])
    return "".join(output)


def normalize_fenced_code_blocks(text: str) -> str:
    """Normalize completed fences to standard triple-backtick fences."""
    def normalize(block: FencedCodeBlock) -> str:
        if not block.complete:
            return block.raw
        body = block.body.rstrip("\r\n")
        fence = _BACKTICK * 3
        return f"{fence}{block.info}\n{body}\n{fence}"

    return replace_fenced_code_blocks(text, normalize)


def mask_fenced_code_blocks(text: str) -> str:
    """Replace fenced block characters with spaces while preserving line breaks."""
    def mask(block: FencedCodeBlock) -> str:
        return "".join("\n" if char == "\n" else "\r" if char == "\r" else " " for char in block.raw)

    return replace_fenced_code_blocks(text, mask)
