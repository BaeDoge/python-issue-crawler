"""Validate repository-internal path references in generated articles.

This module intentionally has no dependency on the LLM/runtime configuration so its
path checks can be tested without an OmniRoute token.
"""
from __future__ import annotations

import re

_REPO_PATH_MENTION_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:ch\d{2,}|appendix-[A-Z]|setup|pkg|\.github)(?:/[A-Za-z0-9_.+@-]+)+)"
)


def find_unverified_repository_paths(
    text: str,
    repository_paths: list[str] | None,
) -> list[str]:
    """Return path-like mentions that are absent from the supplied Git tree."""
    if not repository_paths:
        return []

    known_paths: set[str] = set()
    for path in repository_paths:
        normalized = path.strip().strip("/")
        if not normalized:
            continue
        known_paths.add(normalized)
        parts = normalized.split("/")
        for depth in range(1, len(parts)):
            known_paths.add("/".join(parts[:depth]))

    missing = set()
    for match in _REPO_PATH_MENTION_RE.finditer(text or ""):
        path = match.group(1).rstrip(".,:;!?")
        if path and path not in known_paths:
            missing.add(path)
    return sorted(missing)
