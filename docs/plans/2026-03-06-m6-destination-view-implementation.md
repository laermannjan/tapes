# M6: Destination View Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a destination view toggled by `tab` that shows computed file destination paths instead of metadata columns, with actions to resolve missing fields and confirm processing.

**Architecture:** A `dest_mode` boolean on `GridApp` toggles between metadata and destination views. A new `render_dest_row()` function handles destination-view rendering. A `compute_dest_path()` function applies `str.format_map` to configured templates. Config gains template strings and operation mode. The footer adapts its keybindings per view and state.

**Tech Stack:** Same as existing -- Textual, Rich Text, Pydantic config. No new dependencies.

---

## Task 1: Add template and operation config fields

**Files:**
- Modify: `tapes/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the test**

Add to `tests/test_config.py`:

```python
from tapes.config import TapesConfig, LibraryConfig


def test_library_config_defaults():
    cfg = TapesConfig()
    assert cfg.library.movie_template == "{title} ({year})/{title} ({year}).{ext}"
    assert cfg.library.tv_template == (
        "{title} ({year})/Season {season:02d}/"
        "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    assert cfg.library.operation == "copy"


def test_library_config_custom():
    cfg = TapesConfig(library=LibraryConfig(operation="move", movie_template="{title}.{ext}"))
    assert cfg.library.operation == "move"
    assert cfg.library.movie_template == "{title}.{ext}"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: AttributeError on `movie_template`

**Step 3: Implement**

In `tapes/config.py`, update `LibraryConfig`:

```python
class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""
    movie_template: str = "{title} ({year})/{title} ({year}).{ext}"
    tv_template: str = (
        "{title} ({year})/Season {season:02d}/"
        "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    operation: str = "copy"  # copy | move | link | hardlink
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```
git add tapes/config.py tests/test_config.py
git commit -m "feat(config): add template and operation fields to LibraryConfig"
```

---

## Task 2: Destination path computation

**Files:**
- Create: `tapes/ui/dest.py`
- Test: `tests/test_ui/test_dest.py`

**Step 1: Write the test**

```python
"""Tests for destination path computation."""
from tapes.ui.dest import compute_dest_path
from tapes.ui.models import GridRow, RowKind
from tapes.models import FileEntry, FileMetadata, ImportGroup
from pathlib import Path


def _row(path, title=None, year=None, season=None, episode=None,
         episode_title=None, media_type="movie"):
    meta = FileMetadata(
        title=title, year=year, season=season, episode=episode,
        media_type=media_type,
    )
    group = ImportGroup(metadata=meta)
    entry = FileEntry(path=Path(path), metadata=meta)
    group.add_file(entry)
    return GridRow(kind=RowKind.FILE, entry=entry, group=group)


def test_movie_dest_path():
    row = _row("Dune.2021.mkv", title="Dune", year=2021)
    template = "{title} ({year})/{title} ({year}).{ext}"
    result = compute_dest_path(row, template)
    assert result == "Dune (2021)/Dune (2021).mkv"


def test_tv_dest_path():
    row = _row("bb.s01e01.mkv", title="Breaking Bad", year=2008,
               season=1, episode=1, episode_title="Pilot", media_type="episode")
    template = (
        "{title} ({year})/Season {season:02d}/"
        "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    result = compute_dest_path(row, template)
    assert result == "Breaking Bad (2008)/Season 01/Breaking Bad - S01E01 - Pilot.mkv"


def test_missing_fields_returns_error():
    row = _row("test.mkv", title="Test")  # missing year
    template = "{title} ({year})/{title} ({year}).{ext}"
    result = compute_dest_path(row, template)
    assert result is None


def test_missing_fields_list():
    from tapes.ui.dest import missing_template_fields
    row = _row("test.mkv", title="Test")  # missing year
    template = "{title} ({year})/{title} ({year}).{ext}"
    missing = missing_template_fields(row, template)
    assert missing == ["year"]


def test_missing_fields_episode():
    row = _row("test.mkv", title="Test", year=2020, season=1, episode=1,
               media_type="episode")  # missing episode_title
    template = "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    missing = missing_template_fields(row, template)
    assert missing == ["episode_title"]


def test_fill_unknown():
    from tapes.ui.dest import compute_dest_path_with_unknown
    row = _row("test.mkv", title="Test")
    template = "{title} ({year})/{title} ({year}).{ext}"
    result = compute_dest_path_with_unknown(row, template)
    assert result == "Test (unknown)/Test (unknown).mkv"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_dest.py -v`
Expected: ImportError

**Step 3: Implement**

Create `tapes/ui/dest.py`:

```python
"""Destination path computation for the grid TUI."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from tapes.ui.models import GridRow


def _row_fields(row: GridRow) -> dict[str, str | int]:
    """Extract template fields from a GridRow."""
    ext = PurePosixPath(row.filepath).suffix.lstrip(".")
    fields: dict[str, str | int] = {"ext": ext}
    if row.title is not None:
        fields["title"] = row.title
    if row.year is not None:
        fields["year"] = row.year
    if row.season is not None:
        fields["season"] = row.season
    if row.episode is not None and isinstance(row.episode, int):
        fields["episode"] = row.episode
    if row.episode_title is not None:
        fields["episode_title"] = row.episode_title
    return fields


def _template_field_names(template: str) -> list[str]:
    """Extract field names referenced in a template string."""
    return list(dict.fromkeys(
        m.group(1).split(":")[0]
        for m in re.finditer(r"\{(\w+[^}]*)\}", template)
    ))


def missing_template_fields(row: GridRow, template: str) -> list[str]:
    """Return list of field names required by template but missing from row."""
    available = _row_fields(row)
    needed = _template_field_names(template)
    return [f for f in needed if f not in available]


def compute_dest_path(row: GridRow, template: str) -> str | None:
    """Compute destination path from template and row fields.

    Returns None if any required field is missing.
    """
    fields = _row_fields(row)
    needed = _template_field_names(template)
    if any(f not in fields for f in needed):
        return None
    return template.format_map(fields)


def compute_dest_path_with_unknown(row: GridRow, template: str) -> str:
    """Compute destination path, substituting 'unknown' for missing fields."""
    fields = _row_fields(row)
    needed = _template_field_names(template)
    fill = {f: fields.get(f, "unknown") for f in needed}
    return template.format_map(fill)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_dest.py -v`
Expected: PASS

**Step 5: Commit**

```
git add tapes/ui/dest.py tests/test_ui/test_dest.py
git commit -m "feat(ui): add destination path computation from templates"
```

---

## Task 3: Destination row renderer

**Files:**
- Modify: `tapes/ui/render.py`
- Test: `tests/test_ui/test_render.py`

**Step 1: Write the test**

Add to `tests/test_ui/test_render.py`:

```python
from tapes.ui.render import render_dest_row, COL_WIDTHS, FIELD_COLS


def test_render_dest_row_valid_path():
    row = _file_row("movies/Dune.mkv", title="Dune", year=2021)
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path="Dune (2021)/Dune (2021).mkv", missing=None,
    )
    assert "copy" in text.plain
    assert "Dune.mkv" in text.plain
    assert "Dune (2021)/Dune (2021).mkv" in text.plain


def test_render_dest_row_missing_fields():
    row = _file_row("test.mkv", title="Test")
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path=None, missing=["year"],
    )
    assert "copy" in text.plain
    assert "(missing:" in text.plain
    assert "year" in text.plain


def test_render_dest_row_skipped():
    row = _file_row("test.mkv", title="Test")
    text = render_dest_row(
        row, is_cursor_row=False, operation="skip",
        dest_path=None, missing=None, skipped=True,
    )
    assert "skip" in text.plain
    assert "(skipped)" in text.plain


def test_render_dest_row_with_unknown():
    row = _file_row("test.mkv", title="Test")
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path="Test (unknown)/Test (unknown).mkv",
        missing=None, unknown_fields=["year"],
    )
    assert "copy" in text.plain
    # "unknown" should be present in the path
    assert "unknown" in text.plain


def test_render_dest_match_row():
    """Match sub-rows also show destination path in dest view."""
    from tapes.ui.models import GridRow, RowKind
    from tapes.models import ImportGroup, FileMetadata
    group = ImportGroup(metadata=FileMetadata(title="Test"))
    row = GridRow(
        kind=RowKind.MATCH, group=group,
        match_fields={"title": "Test", "year": 2021},
    )
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path="Test (2021)/Test (2021).mkv", missing=None,
    )
    assert "(match)" in text.plain
    assert "Test (2021)" in text.plain
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_render.py::test_render_dest_row_valid_path -v`
Expected: ImportError on `render_dest_row`

**Step 3: Implement**

Add to `tapes/ui/render.py`:

```python
# Combined width of all metadata columns (used as single dest path column)
DEST_COL_WIDTH = sum(COL_WIDTHS[c] for c in FIELD_COLS)


def render_dest_row(
    row: GridRow,
    is_cursor_row: bool,
    operation: str,
    dest_path: str | None,
    missing: list[str] | None,
    *,
    skipped: bool = False,
    unknown_fields: list[str] | None = None,
) -> Text:
    """Render a row in destination view."""
    t = Text()
    row_bg = BG_ROW_CUR if is_cursor_row else None

    is_comp = row.kind == RowKind.FILE and row.is_companion
    base_style = "#555555" if is_comp else "#888888"
    bright_style = "#888888" if is_comp else "#dddddd"

    if row.kind == RowKind.BLANK:
        total = COL_WIDTHS["status"] + COL_WIDTHS["filepath"] + DEST_COL_WIDTH
        _col(t, "", total, "#333333")
        return t

    if row.kind == RowKind.NO_MATCH:
        _col(t, " \u23bf  ", COL_WIDTHS["status"], "#333333")
        _col(t, "(no match)", COL_WIDTHS["filepath"], "#cc5555")
        _col(t, "", DEST_COL_WIDTH, "#333333")
        return t

    # Status column: operation or skip
    if skipped:
        op_style = "#555555"
    else:
        op_style = "#888888"
    op_display = _pad(operation, COL_WIDTHS["status"])
    op_full = f"{op_style} on {row_bg}" if row_bg else op_style
    t.append(op_display, style=op_full)

    # Filepath column (match rows show "(match)")
    if row.kind == RowKind.MATCH:
        _col(t, "(match)", COL_WIDTHS["filepath"], "#ccaa33", bg=row_bg)
    else:
        fp = row.filepath
        p = PurePosixPath(fp)
        if len(p.parts) > 1 and row.is_video:
            dir_part = str(p.parent) + "/"
            padded_fp = _pad(dir_part + p.name, COL_WIDTHS["filepath"])
            fp_text = Text()
            dir_len = min(len(dir_part), len(padded_fp))
            fp_text.append(
                padded_fp[:dir_len],
                style=f"#555555 on {row_bg}" if row_bg else "#555555",
            )
            fp_text.append(
                padded_fp[dir_len:],
                style=f"{bright_style} on {row_bg}" if row_bg else bright_style,
            )
            t.append_text(fp_text)
        else:
            style = base_style if is_comp else bright_style
            _col(t, fp, COL_WIDTHS["filepath"], style, bg=row_bg)

    # Destination path column
    if skipped:
        _col(t, "(skipped)", DEST_COL_WIDTH, "#555555", bg=row_bg, pad_left=2)
    elif missing:
        missing_str = "(missing: " + ", ".join(missing) + ")"
        _col(t, missing_str, DEST_COL_WIDTH, "#cc5555", bg=row_bg, pad_left=2)
    elif dest_path is not None:
        if unknown_fields:
            # Render with "unknown" highlighted in yellow
            _render_dest_with_unknown(t, dest_path, DEST_COL_WIDTH, bright_style, row_bg)
        else:
            _col(t, dest_path, DEST_COL_WIDTH, bright_style, bg=row_bg, pad_left=2)
    else:
        _col(t, "", DEST_COL_WIDTH, "#333333", bg=row_bg)

    return t


def _render_dest_with_unknown(
    t: Text, path: str, width: int, style: str, bg: str | None,
) -> None:
    """Render a destination path with 'unknown' segments highlighted yellow."""
    padded = _pad("  " + path, width)
    full_style = f"{style} on {bg}" if bg else style
    warn_style = f"#ccaa33 on {bg}" if bg else "#ccaa33"
    # Split on 'unknown' and render segments
    parts = padded.split("unknown")
    for i, part in enumerate(parts):
        t.append(part, style=full_style)
        if i < len(parts) - 1:
            t.append("unknown", style=warn_style)
```

Also add the `PurePosixPath` import if not already at top (it is).

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_render.py -v`
Expected: PASS

**Step 5: Commit**

```
git add tapes/ui/render.py tests/test_ui/test_render.py
git commit -m "feat(ui): add render_dest_row for destination view"
```

---

## Task 4: GridApp destination view toggle and state

**Files:**
- Modify: `tapes/ui/grid.py`
- Test: `tests/test_ui/test_grid.py`

**Step 1: Write the test**

Add to `tests/test_ui/test_grid.py`:

```python
async def test_tab_toggles_dest_view():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert app.dest_mode is False
        await pilot.press("tab")
        assert app.dest_mode is True
        await pilot.press("tab")
        assert app.dest_mode is False


async def test_dest_view_disables_edit():
    """Edit key should be ignored in dest view."""
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("e")
        assert app.editing is False


async def test_dest_view_disables_query():
    """Query should be ignored in dest view."""
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("q")
        # No crash, no match rows
        match_rows = [r for r in app._rows if r.kind == RowKind.MATCH]
        assert len(match_rows) == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_grid.py::test_tab_toggles_dest_view -v`
Expected: AttributeError on `dest_mode`

**Step 3: Implement**

In `tapes/ui/grid.py`:

1. Add `dest_mode` property and state:

```python
# In GridApp.__init__, add:
self._dest_mode: bool = False
```

2. Add `dest_mode` property:

```python
@property
def dest_mode(self) -> bool:
    return self._dest_mode
```

3. Add `tab` binding:

```python
Binding("tab", "toggle_dest", "Toggle view", show=False),
```

4. Add `action_toggle_dest`:

```python
def action_toggle_dest(self) -> None:
    """Toggle between metadata and destination view."""
    if self._editing:
        return
    self._dest_mode = not self._dest_mode
    if self._grid:
        self._grid._dest_mode = self._dest_mode
        self._grid.refresh_grid()
    self._refresh_footer()
```

5. Add `_dest_mode` to `GridWidget.__init__`:

```python
self._dest_mode: bool = False
```

6. Guard `action_start_edit`, `action_query`, `action_query_all`, `action_toggle_select`, `action_select_group`, `action_select_season`, `action_select_show` with:

```python
if self._dest_mode:
    return
```

7. Update `GridWidget.render_grid` to call `render_dest_row` when in dest mode. Import `render_dest_row` and the dest computation functions. For each FILE row, compute the dest path and call `render_dest_row` instead of `render_row`.

In `GridWidget.render_grid`, the dest-mode branch:

```python
if self._dest_mode:
    from tapes.ui.dest import compute_dest_path, missing_template_fields
    from tapes.ui.render import render_dest_row
    from tapes.config import TapesConfig
    # Use default config for now (will be passed in later)
    cfg = self._get_config()
    for i, row in enumerate(self.rows):
        if i > 0:
            out.append("\n")
        if row.kind == RowKind.BLANK:
            line = render_dest_row(row, is_cursor_row=False,
                                   operation="", dest_path=None, missing=None)
        elif row.kind in (RowKind.NO_MATCH,):
            line = render_dest_row(row, is_cursor_row=(i == self._cursor_row),
                                   operation="", dest_path=None, missing=None)
        elif row.kind == RowKind.MATCH:
            # Compute dest from match fields
            template = self._get_template(row)
            dest = self._compute_match_dest(row, template)
            line = render_dest_row(row, is_cursor_row=(i == self._cursor_row),
                                   operation=cfg.library.operation,
                                   dest_path=dest, missing=None)
        else:
            template = self._get_template(row)
            dest = compute_dest_path(row, template)
            missing = missing_template_fields(row, template) if dest is None else None
            skipped = getattr(row, '_skipped', False)
            op = "skip" if skipped else cfg.library.operation
            line = render_dest_row(row, is_cursor_row=(i == self._cursor_row),
                                   operation=op, dest_path=dest, missing=missing,
                                   skipped=skipped)
        out.append_text(line)
    return out
```

This is complex -- better to move template/config logic to `GridApp` and pass computed data to `GridWidget`. Instead, add a method on `GridApp` that pre-computes dest info per row and stores it for `GridWidget` to use.

Actually, keep it simpler. Pass config to `GridApp`, store it, and have `GridWidget` access it through a reference. Here's the cleaner approach:

In `GridApp.__init__`, accept optional config:

```python
def __init__(self, groups: list[ImportGroup], *, config: TapesConfig | None = None, **kwargs) -> None:
    super().__init__(**kwargs)
    self._groups = groups
    self._rows = build_grid_rows(groups)
    self._config = config or TapesConfig()
    # ... rest unchanged
```

Add helper on `GridApp`:

```python
def _get_template(self, row: GridRow) -> str:
    """Return the appropriate template for a row based on media_type."""
    meta = row._meta() if row.kind == RowKind.FILE else (row.group.metadata if row.group else FileMetadata())
    if meta.media_type == "episode":
        return self._config.library.tv_template
    return self._config.library.movie_template
```

Update `GridWidget` to accept a `dest_renderer` callback from `GridApp`, or simpler: have `GridApp._refresh_grid()` pre-compute dest data and pass it to the widget.

The simplest approach: add a `_dest_data` dict on `GridWidget` that maps row index to `(operation, dest_path, missing, skipped, unknown_fields)`. `GridApp` populates this before each refresh when in dest mode.

```python
# In GridWidget.__init__:
self._dest_data: dict[int, tuple[str, str | None, list[str] | None, bool, list[str] | None]] = {}
```

In `GridApp`, add:

```python
def _compute_dest_data(self) -> None:
    """Pre-compute destination data for all rows."""
    from tapes.ui.dest import compute_dest_path, compute_dest_path_with_unknown, missing_template_fields
    if not self._grid:
        return
    data: dict[int, tuple[str, str | None, list[str] | None, bool, list[str] | None]] = {}
    op = self._config.library.operation
    for i, row in enumerate(self._rows):
        if row.kind == RowKind.BLANK:
            continue
        if row.kind == RowKind.NO_MATCH:
            data[i] = ("", None, None, False, None)
            continue
        if row.kind == RowKind.MATCH:
            # Use match_fields to compute a preview dest
            template = self._get_template(row)
            # Build a temporary row-like with match fields for preview
            dest = self._compute_match_dest(row, template)
            data[i] = (op, dest, None, False, None)
            continue
        # FILE row
        skipped = getattr(row, '_skipped', False)
        if skipped:
            data[i] = ("skip", None, None, True, None)
            continue
        template = self._get_template(row)
        filled_unknown = getattr(row, '_filled_unknown', False)
        if filled_unknown:
            dest = compute_dest_path_with_unknown(row, template)
            missing = missing_template_fields(row, template)
            data[i] = (op, dest, None, False, missing if missing else None)
        else:
            dest = compute_dest_path(row, template)
            if dest is None:
                missing = missing_template_fields(row, template)
                data[i] = (op, None, missing, False, None)
            else:
                data[i] = (op, dest, None, False, None)
    self._grid._dest_data = data
```

This is getting too detailed for the plan document. Let me simplify the tasks.

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_grid.py -v`
Expected: PASS

**Step 5: Commit**

```
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): add tab toggle for destination view"
```

---

## Task 5: Destination view rendering in GridWidget

**Files:**
- Modify: `tapes/ui/grid.py`
- Modify: `tapes/ui/render.py`
- Test: `tests/test_ui/test_grid.py`

**Step 1: Write the test**

```python
async def test_dest_view_shows_dest_paths():
    """In dest view, file rows show computed destination paths."""
    from tapes.config import TapesConfig
    app = GridApp(_groups(), config=TapesConfig())
    async with app.run_test() as pilot:
        await pilot.press("tab")
        # Dune has title+year, so should compute a path
        # The grid should render without error
        assert app.dest_mode is True
```

**Step 2: Implement the rendering pipeline**

Wire `GridApp._compute_dest_data()` into the refresh cycle. When `_dest_mode` is True, call `_compute_dest_data()` before `refresh_grid()`. In `GridWidget.render_grid()`, check `_dest_mode` and use `render_dest_row` with data from `_dest_data` dict.

**Step 3: Update column header for dest view**

In `GridColumnHeader`, check a `dest_mode` attribute. When True, show `"  destination"` spanning the metadata columns instead of individual field headers.

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/ -v`
Expected: PASS

**Step 5: Commit**

```
git add tapes/ui/grid.py tapes/ui/render.py tests/test_ui/test_grid.py
git commit -m "feat(ui): render destination paths in dest view"
```

---

## Task 6: Destination view footer

**Files:**
- Modify: `tapes/ui/grid.py`
- Test: `tests/test_ui/test_grid.py`

**Step 1: Write the test**

```python
async def test_dest_footer_shows_tab_hint():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("tab")
        footer = app.query_one(GridFooter)
        text = footer.render()
        assert "tab" in text.plain
        assert "metadata" in text.plain
```

**Step 2: Implement**

Update `GridFooter` to accept `dest_mode` state. When `dest_mode` is True:

- Count uncertain (`??`) rows, no-match rows, and rows with missing fields
- Show appropriate keybindings based on state:
  - Has uncertain: `[A] accept all  [R] reject all  [enter] accept  [bksp] reject  [tab] metadata`
  - Has missing (no uncertain): `[I] ignore missing  [F] fill unknown  [tab] metadata`
  - All resolved: `[=] process N files  [tab] metadata`

Add `update_dest_mode(dest_mode, dest_data)` method to `GridFooter`.

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/ -v`
Expected: PASS

**Step 4: Commit**

```
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): destination view footer with context-aware hints"
```

---

## Task 7: Accept-all and reject-all uncertain matches

**Files:**
- Modify: `tapes/ui/grid.py`
- Test: `tests/test_ui/test_grid.py`

**Step 1: Write the test**

Use the existing `_groups_with_uncertain()` helper (or create one). The test data needs groups that produce uncertain matches after query.

```python
def _groups_with_episodes():
    """Groups that produce uncertain matches (Breaking Bad)."""
    bb1_meta = FileMetadata(title="Breaking Bad", year=2008, season=1,
                            episode=1, media_type="episode")
    bb1 = ImportGroup(metadata=bb1_meta)
    bb1.add_file(FileEntry(path=Path("bb/S01E01.mkv"), metadata=bb1_meta))

    bb2_meta = FileMetadata(title="Breaking Bad", year=2008, season=1,
                            episode=2, media_type="episode")
    bb2 = ImportGroup(metadata=bb2_meta)
    bb2.add_file(FileEntry(path=Path("bb/S01E02.mkv"), metadata=bb2_meta))

    return [bb1, bb2]


async def test_accept_all_uncertain():
    app = GridApp(_groups_with_episodes())
    async with app.run_test() as pilot:
        # Query all to get uncertain matches
        await pilot.press("Q")
        uncertain = [r for r in app._rows if r.status == RowStatus.UNCERTAIN]
        assert len(uncertain) > 0

        # Switch to dest view and accept all
        await pilot.press("tab")
        await pilot.press("A")

        # All should be auto-accepted now
        uncertain_after = [r for r in app._rows if r.status == RowStatus.UNCERTAIN]
        assert len(uncertain_after) == 0
        match_rows = [r for r in app._rows if r.kind == RowKind.MATCH]
        assert len(match_rows) == 0


async def test_reject_all_uncertain():
    app = GridApp(_groups_with_episodes())
    async with app.run_test() as pilot:
        await pilot.press("Q")
        await pilot.press("tab")
        await pilot.press("R")

        uncertain_after = [r for r in app._rows if r.status == RowStatus.UNCERTAIN]
        assert len(uncertain_after) == 0
        raw = [r for r in app._rows if r.kind == RowKind.FILE and r.status == RowStatus.RAW]
        assert len(raw) == 2  # reverted to RAW
```

**Step 2: Implement**

Add bindings (only active in dest mode):

```python
Binding("A", "accept_all_uncertain", "Accept all", show=False, key_display="shift+a"),
Binding("R", "reject_all_uncertain", "Reject all", show=False, key_display="shift+r"),
```

Note: `A` is already bound to `action_select_show`. In dest mode, `A` should mean accept-all instead. Handle this by checking `_dest_mode` in both actions:

- `action_select_show`: add `if self._dest_mode: return` guard
- `action_accept_all_uncertain`: add `if not self._dest_mode: return` guard

Actually, since `A` is already bound to `select_show`, we need a different approach. Rebind: in dest mode, `A` means accept-all. Override `action_select_show` to dispatch:

```python
def action_select_show(self) -> None:
    if self._dest_mode:
        self._accept_all_uncertain()
        return
    # ... existing select show logic
```

Or use a separate key. Let's keep `A` dual-purpose since selection is disabled in dest mode anyway.

Implement `_accept_all_uncertain()`:

```python
def _accept_all_uncertain(self) -> None:
    """Accept all uncertain match sub-rows."""
    import copy
    self._undo_rows = copy.deepcopy(self._rows)

    match_rows = [(i, r) for i, r in enumerate(self._rows) if r.kind == RowKind.MATCH]
    for _, match_row in reversed(match_rows):
        for idx in match_row.owned_row_indices:
            self._rows[idx].apply_match(match_row.match_fields)
    # Remove all MATCH rows
    self._rows = [r for r in self._rows if r.kind != RowKind.MATCH]
    self._reindex_owned_rows()
    if self._grid:
        self._grid.rows = self._rows
        self._grid.refresh_grid()
    self._refresh_footer()
```

Similar for `_reject_all_uncertain()`.

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_grid.py -v`
Expected: PASS

**Step 4: Commit**

```
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): accept-all and reject-all uncertain matches in dest view"
```

---

## Task 8: Ignore-missing and fill-unknown actions

**Files:**
- Modify: `tapes/ui/grid.py`
- Modify: `tapes/ui/models.py`
- Test: `tests/test_ui/test_grid.py`

**Step 1: Write the test**

```python
async def test_ignore_missing_marks_skipped():
    """I in dest view marks rows with missing fields as skipped."""
    # Create a group with missing year
    meta = FileMetadata(title="Unknown Movie", media_type="movie")
    g = ImportGroup(metadata=meta)
    g.add_file(FileEntry(path=Path("movie.mkv"), metadata=meta))
    app = GridApp([g])
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("I")
        # Row should be marked skipped
        assert app._rows[0]._skipped is True


async def test_fill_unknown():
    """F in dest view fills missing fields with 'unknown'."""
    meta = FileMetadata(title="Unknown Movie", media_type="movie")
    g = ImportGroup(metadata=meta)
    g.add_file(FileEntry(path=Path("movie.mkv"), metadata=meta))
    app = GridApp([g])
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("F")
        assert app._rows[0]._filled_unknown is True
```

**Step 2: Implement**

Add `_skipped` and `_filled_unknown` flags to `GridRow`:

```python
# In GridRow dataclass:
_skipped: bool = False
_filled_unknown: bool = False
```

Add bindings (only active in dest mode, when no uncertain matches):

```python
Binding("I", "ignore_missing", "Ignore missing", show=False),
Binding("F", "fill_unknown", "Fill unknown", show=False),
```

Implement actions:

```python
def action_ignore_missing(self) -> None:
    if not self._dest_mode or not self._grid:
        return
    import copy
    self._undo_rows = copy.deepcopy(self._rows)
    from tapes.ui.dest import missing_template_fields
    for row in self._rows:
        if row.kind != RowKind.FILE:
            continue
        template = self._get_template(row)
        if missing_template_fields(row, template):
            row._skipped = True
    self._compute_dest_data()
    self._grid.refresh_grid()
    self._refresh_footer()


def action_fill_unknown(self) -> None:
    if not self._dest_mode or not self._grid:
        return
    import copy
    self._undo_rows = copy.deepcopy(self._rows)
    from tapes.ui.dest import missing_template_fields
    for row in self._rows:
        if row.kind != RowKind.FILE:
            continue
        template = self._get_template(row)
        if missing_template_fields(row, template):
            row._filled_unknown = True
    self._compute_dest_data()
    self._grid.refresh_grid()
    self._refresh_footer()
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_grid.py -v`
Expected: PASS

**Step 4: Commit**

```
git add tapes/ui/grid.py tapes/ui/models.py tests/test_ui/test_grid.py
git commit -m "feat(ui): ignore-missing and fill-unknown actions in dest view"
```

---

## Task 9: Process confirmation flow

**Files:**
- Modify: `tapes/ui/grid.py`
- Test: `tests/test_ui/test_grid.py`

**Step 1: Write the test**

```python
async def test_process_confirm_flow():
    """= in dest view enters confirmation, second = exits app."""
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # Query all to fill metadata (auto-accept)
        await pilot.press("Q")
        await pilot.press("tab")
        # First = enters confirmation
        await pilot.press("=")
        assert app._confirming is True
        # Esc cancels
        await pilot.press("escape")
        assert app._confirming is False
        assert app.dest_mode is True


async def test_process_blocked_with_uncertain():
    """= should not work when uncertain matches exist."""
    app = GridApp(_groups_with_episodes())
    async with app.run_test() as pilot:
        await pilot.press("Q")
        await pilot.press("tab")
        await pilot.press("=")
        assert app._confirming is False  # blocked
```

**Step 2: Implement**

Add `_confirming` state to `GridApp`:

```python
self._confirming: bool = False
```

Add binding:

```python
Binding("=", "process", "Process", show=False),
```

Implement:

```python
def action_process(self) -> None:
    if not self._dest_mode or not self._grid:
        return
    if self._confirming:
        # Second press: execute (dry-run for now)
        self._execute_process()
        return
    # Check blockers
    has_uncertain = any(r.kind == RowKind.MATCH for r in self._rows)
    if has_uncertain:
        return  # blocked
    from tapes.ui.dest import missing_template_fields
    has_missing = any(
        r.kind == RowKind.FILE and not r._skipped and not r._filled_unknown
        and missing_template_fields(r, self._get_template(r))
        for r in self._rows
    )
    if has_missing:
        return  # blocked
    self._confirming = True
    self._refresh_footer()


def _execute_process(self) -> None:
    """Dry-run: print summary and exit."""
    processable = [r for r in self._rows
                   if r.kind == RowKind.FILE and not r._skipped]
    op = self._config.library.operation
    self.exit(message=f"{op} {len(processable)} files")


def action_cancel_edit(self) -> None:
    # ... existing code, but also handle confirming:
    if self._confirming:
        self._confirming = False
        self._refresh_footer()
        return
    # ... rest unchanged
```

Update footer to show confirmation state:

```python
# In GridFooter, when confirming:
# "copy 12 files to library? [=] confirm  [esc] cancel"
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_grid.py -v`
Expected: PASS

**Step 4: Commit**

```
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): process confirmation flow with dry-run exit"
```

---

## Task 10: Wire config into CLI grid command

**Files:**
- Modify: `tapes/cli.py`
- Test: manual

**Step 1: Implement**

Pass config to `GridApp` in the CLI:

```python
# In grid_cmd:
from tapes.ui.grid import GridApp
tui = GridApp(groups, config=cfg)
tui.run()
```

Update `_mock_groups()` to have some episodes (already has Breaking Bad).

**Step 2: Test manually**

Run: `uv run tapes grid`
- Press `tab` to toggle dest view
- Verify paths appear for Dune and Arrival
- Verify `(missing: ...)` for rows without metadata
- Press `tab` back to metadata view

**Step 3: Commit**

```
git add tapes/cli.py
git commit -m "feat(cli): pass config to GridApp for dest view"
```

---

## Task 11: Update grid TUI plan with M6 notes

**Files:**
- Modify: `docs/plans/2026-03-06-grid-tui.md`

Update the M6 section with implementation notes (like M1-M5).

```
git add docs/plans/2026-03-06-grid-tui.md
git commit -m "docs: update grid TUI plan with M6 implementation notes"
```
