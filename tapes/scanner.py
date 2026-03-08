"""File scanner -- recursively find files under a root path."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"})

SAMPLE_RE = re.compile(r"(?i)(^sample$|^sample[.\-_ ]|[.\-_ ]sample[.\-_ ]|[.\-_ ]sample$)")


def _is_hidden_path(path: Path, root: Path) -> bool:
    """Return True if any component between root and path starts with '.'."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in rel.parts[:-1])


def _is_sample(path: Path) -> bool:
    """Return True if the filename stem matches the sample pattern."""
    return SAMPLE_RE.search(path.stem) is not None


def _is_video(path: Path) -> bool:
    """Return True if the file has a video extension (case-insensitive)."""
    return path.suffix.lower() in VIDEO_EXTENSIONS


def _matches_ignore(path: Path, ignore_patterns: list[str]) -> bool:
    """Return True if the filename matches any of the ignore patterns."""
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in ignore_patterns)


def scan(
    root: Path,
    ignore_patterns: list[str] | None = None,
) -> list[Path]:
    """Find files recursively under *root*.

    - Finds all files, not just video files.
    - Excludes files matching *ignore_patterns* (fnmatch against filename).
    - Excludes sample files, but only if they are video files.
    - Excludes files inside hidden directories (starting with '.').
    - If *root* is a single file, checks it directly.
    - Returns a sorted list of Path objects.
    """
    if ignore_patterns is None:
        ignore_patterns = []

    if root.is_file():
        if _matches_ignore(root, ignore_patterns):
            return []
        if _is_video(root) and _is_sample(root):
            return []
        return [root]

    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_hidden_path(path, root):
            continue
        if _matches_ignore(path, ignore_patterns):
            continue
        if _is_video(path) and _is_sample(path):
            continue
        results.append(path)

    results.sort()
    return results
