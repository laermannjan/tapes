"""Core data models for tapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"}
)
SUBTITLE_EXTENSIONS: frozenset[str] = frozenset(
    {".srt", ".sub", ".idx", ".ssa", ".ass", ".vtt"}
)
METADATA_EXTENSIONS: frozenset[str] = frozenset({".nfo", ".xml"})
ARTWORK_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".png", ".webp"})


def file_role(path: Path) -> str:
    """Determine the role of a file based on its extension."""
    ext = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in SUBTITLE_EXTENSIONS:
        return "subtitle"
    if ext in METADATA_EXTENSIONS:
        return "metadata"
    if ext in ARTWORK_EXTENSIONS:
        return "artwork"
    return "other"


class GroupType(Enum):
    STANDALONE = "standalone"
    MULTI_PART = "multi_part"
    SEASON = "season"


class GroupStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    AUTO_ACCEPTED = "auto_accepted"
    SKIPPED = "skipped"


@dataclass
class FileMetadata:
    """Parsed metadata about a media file."""

    media_type: str | None = None
    title: str | None = None
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    part: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class FileEntry:
    """A single file with its role and optional group back-reference."""

    path: Path
    role: str | None = None
    group: ImportGroup | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.role is None:
            self.role = file_role(self.path)


@dataclass
class ImportGroup:
    """A group of related files to be imported together."""

    metadata: FileMetadata
    group_type: GroupType = GroupType.STANDALONE
    status: GroupStatus = GroupStatus.PENDING
    _files: list[FileEntry] = field(default_factory=list, repr=False)

    @property
    def files(self) -> list[FileEntry]:
        """Return a copy of the internal file list."""
        return list(self._files)

    @property
    def video_files(self) -> list[FileEntry]:
        """Return only video files."""
        return [f for f in self._files if f.role == "video"]

    @property
    def label(self) -> str:
        """Human-readable label for this group."""
        meta = self.metadata
        if meta.title:
            if meta.media_type == "episode" and meta.season is not None:
                return f"{meta.title} S{meta.season:02d}"
            if meta.year is not None:
                return f"{meta.title} ({meta.year})"
            return meta.title
        # Fallback to first video filename
        for f in self._files:
            if f.role == "video":
                return f.path.name
        # Fallback to any filename
        if self._files:
            return self._files[0].path.name
        return "Unknown"

    def add_file(self, entry: FileEntry) -> None:
        """Add a file to this group, setting its back-reference."""
        if entry in self._files:
            return
        # Remove from previous group if any
        if entry.group is not None:
            entry.group.remove_file(entry)
        self._files.append(entry)
        entry.group = self

    def remove_file(self, entry: FileEntry) -> None:
        """Remove a file from this group, clearing its back-reference."""
        try:
            self._files.remove(entry)
        except ValueError:
            return
        entry.group = None
