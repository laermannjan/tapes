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
    NO_MATCH = auto()  # M5: no match found


class RowStatus(Enum):
    RAW = ".."       # guessit only
    AUTO = "**"      # auto-accepted TMDB
    UNCERTAIN = "??" # uncertain match
    EDITED = "!!"    # user-edited
    FROZEN = "--"      # all fields frozen


@dataclass
class GridRow:
    """One visual row in the grid. May be a file or a blank separator."""
    kind: RowKind
    entry: FileEntry | None = None
    group: ImportGroup | None = None
    status: RowStatus = RowStatus.RAW
    edited_fields: set[str] = field(default_factory=set)
    frozen_fields: set[str] = field(default_factory=set)
    _overrides: dict[str, Any] = field(default_factory=dict)
    # Match sub-row fields (only used when kind == MATCH)
    match_fields: dict[str, Any] = field(default_factory=dict)
    match_confidence: float = 0.0
    # Rows owned by this match sub-row (indices populated after build)
    owned_row_indices: list[int] = field(default_factory=list)

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
        if name in self.frozen_fields:
            return
        self._overrides[name] = value
        self.edited_fields.add(name)
        self.status = RowStatus.EDITED

    def apply_match(self, fields: dict[str, Any]) -> None:
        """Apply a TMDB match: set overrides and mark status as AUTO."""
        for name, value in fields.items():
            if name not in self.frozen_fields:
                self._overrides[name] = value
        self.status = RowStatus.AUTO

    def toggle_freeze_field(self, name: str) -> None:
        """Toggle freeze on a single field."""
        if name in self.frozen_fields:
            self.frozen_fields.discard(name)
        else:
            self.frozen_fields.add(name)

    def toggle_freeze_all_fields(self) -> None:
        """Toggle freeze on all fields. Unfreezes all if all are frozen."""
        from tapes.ui.render import FIELD_COLS
        if all(f in self.frozen_fields for f in FIELD_COLS):
            self.frozen_fields.clear()
        else:
            for col in FIELD_COLS:
                self.frozen_fields.add(col)

    def is_frozen(self, name: str) -> bool:
        """Check if a field is frozen."""
        return name in self.frozen_fields

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


def _cluster_key(group: ImportGroup) -> tuple[str, int | None] | None:
    """Return a clustering key for sibling detection.

    Episode groups with the same (title_lower, season) are siblings and
    should not have blank rows between them. Returns None for non-episodes.
    """
    meta = group.metadata
    if meta.media_type == "episode" and meta.title and meta.season is not None:
        return (meta.title.lower(), meta.season)
    return None


def build_grid_rows(groups: list[ImportGroup]) -> list[GridRow]:
    """Convert ImportGroups into a flat list of GridRows.

    Blank separator rows are inserted between groups, except between
    sibling episode groups (same show + season).
    """
    rows: list[GridRow] = []
    prev_key: tuple[str, int | None] | None = None
    for i, group in enumerate(groups):
        cur_key = _cluster_key(group)
        if i > 0:
            if prev_key is None or cur_key is None or prev_key != cur_key:
                rows.append(GridRow(kind=RowKind.BLANK))
        for entry in group.files:
            rows.append(GridRow(kind=RowKind.FILE, entry=entry, group=group))
        prev_key = cur_key
    return rows
