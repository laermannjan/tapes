"""View models for the grid TUI."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

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
    _overrides: dict[str, Any] = field(default_factory=dict)

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

    def set_field(self, name: str, value: Any) -> None:
        """Set an override for a field, mark it edited, update status."""
        self._overrides[name] = value
        self.edited_fields.add(name)
        self.status = RowStatus.EDITED

    def apply_match(self, fields: dict[str, Any]) -> None:
        """Apply a TMDB match: set overrides and mark status as AUTO."""
        for name, value in fields.items():
            self._overrides[name] = value
        self.status = RowStatus.AUTO

    @property
    def title(self) -> str | None:
        if "title" in self._overrides:
            return self._overrides["title"]
        return self._meta().title

    @property
    def year(self) -> int | None:
        if "year" in self._overrides:
            return self._overrides["year"]
        return self._meta().year

    @property
    def season(self) -> int | None:
        if "season" in self._overrides:
            return self._overrides["season"]
        return self._meta().season

    @property
    def episode(self) -> int | list[int] | None:
        if "episode" in self._overrides:
            return self._overrides["episode"]
        return self._meta().episode

    @property
    def episode_title(self) -> str | None:
        if "episode_title" in self._overrides:
            return self._overrides["episode_title"]
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
