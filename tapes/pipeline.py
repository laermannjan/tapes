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
    root: Path,
    config: TapesConfig | None = None,
    *,
    companions: bool = True,
    group: bool = True,
) -> list[ImportGroup]:
    """Orchestrate the import pipeline.

    Passes 1-2 (scan + extract) always run. Passes 3-4 are controlled by flags.
    ``group=True`` implies ``companions=True``.

    Args:
        root: Directory (or single file) to scan.
        config: Optional configuration; defaults are used when None.
        companions: Run pass 3 (companion discovery). Default True.
        group: Run pass 4 (merge criteria). Implies companions. Default True.

    Returns:
        List of ImportGroup objects ready for further processing.
    """
    if config is None:
        config = TapesConfig()

    if group:
        companions = True

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
        grp = ImportGroup(metadata=metadata)
        grp.add_file(FileEntry(path=video_path, metadata=metadata))
        groups.append(grp)

    # Pass 3: Companions -- find and deduplicate across groups
    if companions:
        companion_depth = config.scan.companion_depth
        companion_separators = tuple(config.scan.companion_separators)
        claimed: set[Path] = set()

        for grp in groups:
            for video_entry in grp.video_files:
                comps = find_companions(
                    video_entry.path,
                    max_depth=companion_depth,
                    separators=companion_separators,
                )
                for comp in comps:
                    if comp.path not in claimed:
                        claimed.add(comp.path)
                        grp.add_file(comp)

    # Pass 4: Group -- apply merge criteria
    if group:
        groups = group_files(groups)

    return groups
