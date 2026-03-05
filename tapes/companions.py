"""Companion file discovery via stem-prefix matching."""

from __future__ import annotations

from pathlib import Path

from tapes.models import (
    ARTWORK_EXTENSIONS,
    METADATA_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    FileEntry,
)

COMPANION_EXTENSIONS: frozenset[str] = (
    SUBTITLE_EXTENSIONS | METADATA_EXTENSIONS | ARTWORK_EXTENSIONS | frozenset({".txt"})
)
COMPANION_SEPARATORS: tuple[str, ...] = (".", "_", "-")


def _is_companion(
    candidate: Path,
    video_stem_lower: str,
    video_path: Path,
    separators: tuple[str, ...],
) -> bool:
    """Check whether a candidate file qualifies as a companion."""
    # Must not be the video file itself
    if candidate == video_path:
        return False

    ext = candidate.suffix.lower()

    # Must have a whitelisted extension
    if ext not in COMPANION_EXTENSIONS:
        return False

    # Must not be a video file
    if ext in VIDEO_EXTENSIONS:
        return False

    candidate_stem_lower = candidate.stem.lower()

    # Exact stem match
    if candidate_stem_lower == video_stem_lower:
        return True

    # Stem-prefix + separator match
    if candidate_stem_lower.startswith(video_stem_lower):
        rest = candidate_stem_lower[len(video_stem_lower) :]
        if rest and rest[0] in separators:
            return True

    return False


def _walk_dirs(root: Path, max_depth: int) -> list[Path]:
    """Collect directories to search, up to max_depth levels deep."""
    dirs = [root]
    if max_depth <= 0:
        return dirs

    frontier = [root]
    for _ in range(max_depth):
        next_frontier: list[Path] = []
        for d in frontier:
            try:
                for child in d.iterdir():
                    if child.is_dir():
                        next_frontier.append(child)
                        dirs.append(child)
            except PermissionError:
                continue
        frontier = next_frontier
    return dirs


def find_companions(
    video: Path,
    max_depth: int = 0,
    separators: tuple[str, ...] = COMPANION_SEPARATORS,
) -> list[FileEntry]:
    """Find companion files for a video using stem-prefix matching.

    A file is a companion if:
    - Its stem starts with the video's stem + a separator, OR its stem equals
      the video's stem (case-insensitive)
    - Its extension is in the companion whitelist
    - It is NOT a video file

    Args:
        video: Path to the video file.
        max_depth: How many directory levels below the video's parent to search.
            0 means same directory only.
        separators: Characters that may follow the video stem in a companion's name.

    Returns:
        List of FileEntry objects for each discovered companion.
    """
    root = video.parent
    video_stem_lower = video.stem.lower()

    companions: list[FileEntry] = []
    for directory in _walk_dirs(root, max_depth):
        try:
            for candidate in directory.iterdir():
                if candidate.is_file() and _is_companion(
                    candidate, video_stem_lower, video, separators
                ):
                    companions.append(FileEntry(path=candidate))
        except PermissionError:
            continue

    return companions
