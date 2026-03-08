"""File scanner -- recursively find files under a root path."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"})

SAMPLE_RE = re.compile(r"(?i)(^sample$|^sample[.\-_ ]|[.\-_ ]sample[.\-_ ]|[.\-_ ]sample$)")


def _is_sample(path: Path) -> bool:
    """Return True if the filename stem matches the sample pattern."""
    return SAMPLE_RE.search(path.stem) is not None


def _is_video(path: Path, extensions: frozenset[str] = VIDEO_EXTENSIONS) -> bool:
    """Return True if the file has a video extension (case-insensitive)."""
    return path.suffix.lower() in extensions


def _matches_ignore(path: Path, ignore_patterns: list[str]) -> bool:
    """Return True if the filename matches any of the ignore patterns."""
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in ignore_patterns)


def scan(
    root: Path,
    ignore_patterns: list[str] | None = None,
    video_extensions: list[str] | None = None,
) -> list[Path]:
    """Find files recursively under *root*.

    - Finds all files, not just video files.
    - Excludes files matching *ignore_patterns* (fnmatch against filename).
    - Excludes sample files, but only if they are video files.
    - Excludes files inside hidden directories (starting with '.').
    - If *root* is a single file, checks it directly.
    - Returns a sorted list of Path objects.

    *video_extensions*, if provided, overrides the default ``VIDEO_EXTENSIONS``
    for determining which files count as video (used for sample filtering).
    """
    if ignore_patterns is None:
        ignore_patterns = []

    ext_set: frozenset[str] = frozenset(video_extensions) if video_extensions is not None else VIDEO_EXTENSIONS

    if root.is_file():
        if _matches_ignore(root, ignore_patterns):
            return []
        if _is_video(root, ext_set) and _is_sample(root):
            return []
        return [root]

    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden directories in-place
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        dirnames.sort()

        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            if _matches_ignore(path, ignore_patterns):
                continue
            if _is_video(path, ext_set) and _is_sample(path):
                continue
            results.append(path)

    results.sort()
    return results
