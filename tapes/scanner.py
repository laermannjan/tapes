"""Video file scanner -- recursively find video files under a root path."""

from __future__ import annotations

import re
from pathlib import Path

from tapes.models import VIDEO_EXTENSIONS

SAMPLE_RE = re.compile(
    r"(?i)(^sample$|^sample[.\-_ ]|[.\-_ ]sample[.\-_ ]|[.\-_ ]sample$)"
)


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


def scan(root: Path) -> list[Path]:
    """Find video files recursively under *root*.

    - Includes only files with extensions in VIDEO_EXTENSIONS.
    - Excludes sample files (matched by SAMPLE_RE against the stem).
    - Excludes files inside hidden directories (starting with '.').
    - If *root* is a single file, checks it directly.
    - Returns a sorted list of Path objects.
    """
    if root.is_file():
        if _is_video(root) and not _is_sample(root):
            return [root]
        return []

    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not _is_video(path):
            continue
        if _is_hidden_path(path, root):
            continue
        if _is_sample(path):
            continue
        results.append(path)

    results.sort()
    return results
