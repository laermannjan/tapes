from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict


@dataclass
class MediaGroup:
    directory: Path
    video_files: list[Path] = field(default_factory=list)


def group_media_files(video_files: list[Path]) -> list[MediaGroup]:
    """
    Group video files by their parent directory.
    Files in the same directory form one group (TV season or movie folder).
    """
    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for f in video_files:
        by_dir[f.parent].append(f)

    return [
        MediaGroup(directory=directory, video_files=sorted(files))
        for directory, files in sorted(by_dir.items())
    ]
