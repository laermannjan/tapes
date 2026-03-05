from pathlib import Path
import re

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"}

# Filenames that are clearly sample files — skip them
_SAMPLE_PATTERN = re.compile(r'(?i)(^sample$|^sample[\.\-_ ]|[\.\-_ ]sample[\.\-_ ]|[\.\-_ ]sample$)')


def scan_media_files(root: Path) -> list[Path]:
    """
    Recursively find all video files under root.
    If root is a file, check it directly.
    Excludes sample files (matched by name pattern).
    Returns a sorted list of Path objects.
    """
    if root.is_file():
        if root.suffix.lower() in VIDEO_EXTENSIONS and not _SAMPLE_PATTERN.search(root.stem):
            return [root]
        return []

    found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _SAMPLE_PATTERN.search(path.stem):
            continue
        found.append(path)
    return sorted(found)
