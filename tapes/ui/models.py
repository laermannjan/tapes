"""View models for the grid TUI."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from tapes.models import FileEntry, FileMetadata, ImportGroup


class RowKind(Enum):
    FILE = auto()
    BLANK = auto()
    MATCH = auto()  # M5: uncertain match sub-row


class RowStatus(Enum):
    RAW = ".."       # guessit only
    AUTO = "**"      # auto-accepted TMDB
    UNCERTAIN = "??" # uncertain match
    EDITED = "!!"    # user-edited


@dataclass
class GridRow:
    """One visual row in the grid. May be a file or a blank separator."""
    kind: RowKind
    entry: FileEntry | None = None
    group: ImportGroup | None = None
    status: RowStatus = RowStatus.RAW
    edited_fields: set[str] = field(default_factory=set)

    @property
    def is_video(self) -> bool:
        return self.entry is not None and self.entry.role == "video"

    @property
    def is_companion(self) -> bool:
        return self.entry is not None and self.entry.role != "video"

    def _meta(self) -> FileMetadata:
        if self.entry and self.entry.metadata:
            return self.entry.metadata
        if self.group:
            return self.group.metadata
        return FileMetadata()

    @property
    def title(self) -> str | None:
        return self._meta().title

    @property
    def year(self) -> int | None:
        return self._meta().year

    @property
    def season(self) -> int | None:
        return self._meta().season

    @property
    def episode(self) -> int | list[int] | None:
        return self._meta().episode

    @property
    def episode_title(self) -> str | None:
        return None  # TMDB only, not from guessit

    @property
    def filepath(self) -> str:
        if self.entry:
            return str(self.entry.path)
        return ""


def build_grid_rows(groups: list[ImportGroup]) -> list[GridRow]:
    """Convert ImportGroups into a flat list of GridRows with blank separators."""
    rows: list[GridRow] = []
    for i, group in enumerate(groups):
        if i > 0:
            rows.append(GridRow(kind=RowKind.BLANK))
        for entry in group.files:
            rows.append(GridRow(kind=RowKind.FILE, entry=entry, group=group))
    return rows
