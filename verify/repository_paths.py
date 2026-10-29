"""Validate repository-internal paths mentioned in generated open-source articles."""
from __future__ import annotations

import re


def _repository_path_pattern(repository_paths: list[str]) -> re.Pattern | None:
    roots = {
        path.strip("/").split("/", 1)[0]
        for path in repository_paths
        if path.strip("/") and "/" in path.strip("/")
    }
    alternatives = [re.escape(root) for root in roots]
    # These project-family patterns must also catch a missing root such as appendix-D
    # when the real tree only contains appendix-E.
    alternatives.extend([r"ch\d{2,}", r"appendix-[A-Z]"])
    alternatives.extend(re.escape(root) for root in ("setup", "pkg", ".github"))
    alternatives = sorted(set(alternatives), key=lambda item: (-len(item), item.lower()))
    if not alternatives:
        return None
    root_pattern = "|".join(alternatives)
    return re.compile(
        rf"(?<![A-Za-z0-9_.-])((?:{root_pattern})(?:/[A-Za-z0-9_.+@-]+)+)"
    )


def find_unverified_repository_paths(
    text: str,
    repository_paths: list[str] | None,
) -> list[str]:
    """Return likely internal paths not present in a complete repository tree.

    The caller should only use this as a blocking check when the Git tree was
    fetched successfully and is not truncated. URLs are stripped before matching
    to avoid treating links such as github.com/owner/repo as repository paths.
    """
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

    pattern = _repository_path_pattern(repository_paths)
    if pattern is None:
        return []

    text_without_urls = re.sub(r"https?://[^\s)>\]]+", "", text or "")
    missing = set()
    for match in pattern.finditer(text_without_urls):
        path = match.group(1).rstrip(".,:;!?")
        if path and path not in known_paths:
            missing.add(path)
    return sorted(missing)
