"""Companion file classification and renaming.

Identifies non-video files that accompany a video file (subtitles, artwork,
NFO files, samples) and provides renaming logic for import.
"""

from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path


class Category(str, Enum):
    VIDEO = "video"
    SUBTITLE = "subtitle"
    ARTWORK = "artwork"
    NFO = "nfo"
    SAMPLE = "sample"
    IGNORE = "ignore"
    UNKNOWN = "unknown"


VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts"}

DEFAULT_PATTERNS: dict[Category, list[str]] = {
    Category.SUBTITLE: ["*.srt", "*.ass", "*.vtt", "*.sub", "*.idx", "*.ssa"],
    Category.ARTWORK: [
        "poster.jpg",
        "folder.jpg",
        "fanart.jpg",
        "banner.jpg",
        "thumb.jpg",
    ],
    Category.NFO: ["*.nfo", "*.xml"],
    Category.SAMPLE: ["sample.*", "*-sample.*", "*sample*.*"],
    Category.IGNORE: ["*.url", "*.lnk", "Thumbs.db", ".DS_Store"],
}


@dataclass
class CompanionFile:
    """A non-video file that accompanies a video file."""

    path: Path
    category: Category
    move_by_default: bool
    relative_to_video: Path


def classify_companions(
    video_path: Path, config: dict | None = None
) -> list[CompanionFile]:
    """Find and classify companion files for a video.

    Scans the video's parent directory (recursively) for non-video files,
    classifies them by category, and returns a list of CompanionFile objects.
    Files in the IGNORE category are filtered out.

    Args:
        video_path: Path to the video file.
        config: Optional configuration dict (reserved for future use).

    Returns:
        List of classified companion files, excluding ignored files.
    """
    patterns = DEFAULT_PATTERNS
    move_defaults: dict[Category, bool] = {
        Category.SUBTITLE: True,
        Category.ARTWORK: True,
        Category.NFO: True,
        Category.SAMPLE: False,
        Category.UNKNOWN: False,
    }
    parent = video_path.parent
    companions: list[CompanionFile] = []
    for f in parent.rglob("*"):
        if f == video_path or not f.is_file():
            continue
        if f.suffix.lower() in VIDEO_EXTENSIONS:
            continue
        cat = _categorize(f.name, patterns)
        if cat == Category.IGNORE:
            continue
        companions.append(
            CompanionFile(
                path=f,
                category=cat,
                move_by_default=move_defaults.get(cat, False),
                relative_to_video=f.relative_to(parent),
            )
        )
    return companions


def _categorize(
    filename: str, patterns: dict[Category, list[str]]
) -> Category:
    """Match a filename against category patterns.

    Patterns are checked case-insensitively using fnmatch on lowercased input.
    The first matching category wins. If no pattern matches, returns UNKNOWN.
    """
    lower = filename.lower()
    for cat, pats in patterns.items():
        if any(fnmatch(lower, p.lower()) for p in pats):
            return cat
    return Category.UNKNOWN


def rename_companion(
    original_name: str, dest_stem: str, category: Category
) -> str:
    """Compute a new filename for a companion file.

    Subtitles preserve the language tag (e.g. ``movie.en.srt`` becomes
    ``Dune (2021).en.srt``). NFO files get the destination stem with
    ``.nfo`` extension. All other categories keep their original name.

    Args:
        original_name: Current filename (e.g. ``movie.en.srt``).
        dest_stem: Target stem from the video rename (e.g. ``Dune (2021)``).
        category: The file's classified category.

    Returns:
        The new filename string.
    """
    parts = original_name.split(".")
    if category == Category.SUBTITLE and len(parts) >= 3:
        lang_and_ext = ".".join(parts[-2:])
        return f"{dest_stem}.{lang_and_ext}"
    elif category == Category.NFO:
        return f"{dest_stem}.nfo"
    else:
        return original_name
