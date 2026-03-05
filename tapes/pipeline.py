"""Four-pass import pipeline: scan -> extract -> companions -> group."""

from __future__ import annotations

from pathlib import Path

from tapes.companions import find_companions
from tapes.config import TapesConfig
from tapes.grouper import group_files
from tapes.metadata import extract_metadata
from tapes.models import FileEntry, ImportGroup
from tapes.scanner import scan


def run_pipeline(
    root: Path, config: TapesConfig | None = None
) -> list[ImportGroup]:
    """Orchestrate the four-pass import pipeline.

    Pass 1 -- Scan: find video files under *root*.
    Pass 2 -- Extract: parse metadata from each filename; create one ImportGroup per video.
    Pass 3 -- Companions: discover companion files for each video; deduplicate globally.
    Pass 4 -- Group: apply merge criteria (season merge, multi-part merge).

    Args:
        root: Directory (or single file) to scan.
        config: Optional configuration; defaults are used when None.

    Returns:
        List of ImportGroup objects ready for further processing.
    """
    if config is None:
        config = TapesConfig()

    # Pass 1: Scan
    videos = scan(root)
    if not videos:
        return []

    # Pass 2: Extract metadata and create one group per video
    groups: list[ImportGroup] = []
    for video_path in videos:
        folder_name: str | None = None
        if video_path.parent != root:
            folder_name = video_path.parent.name

        metadata = extract_metadata(video_path.name, folder_name=folder_name)
        group = ImportGroup(metadata=metadata)
        group.add_file(FileEntry(path=video_path))
        groups.append(group)

    # Pass 3: Companions -- find and deduplicate across groups
    companion_depth = config.scan.companion_depth
    companion_separators = tuple(config.scan.companion_separators)
    claimed: set[Path] = set()

    for group in groups:
        for video_entry in group.video_files:
            companions = find_companions(
                video_entry.path,
                max_depth=companion_depth,
                separators=companion_separators,
            )
            for comp in companions:
                if comp.path not in claimed:
                    claimed.add(comp.path)
                    group.add_file(comp)

    # Pass 4: Group -- apply merge criteria
    groups = group_files(groups)

    return groups
