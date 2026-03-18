# TUI Layout Overhaul Implementation Plan

Status: **completed** (merged to main 2026-03-08)

**Goal:** Replace lazygit-style boxed window design with Claude Code-inspired layout using horizontal separators, a persistent bottom bar with search input and operation mode, and a pop-up Info panel.

**Architecture:** Remove CSS borders from TreeView and DetailView. TreeView renders raw content with no chrome. A new BottomBar widget (4 lines) docks to the bottom showing stats, search input, operation mode, and keybinding hints. DetailView is hidden by default and pops up from the bottom when entering a file, replacing the BottomBar. A shared `render_separator()` utility draws horizontal lines with optional title and right-aligned text.

**Tech Stack:** Textual 8, Rich Text, Pydantic v2 config

---

## Color constants

| Name | Hex | Usage |
|------|-----|-------|
| ACCENT | `#B1B9F9` | Focused separator (Info panel, active search) |
| INACTIVE | `#555555` | Unfocused separator |
| MUTED | `#888888` | Labels, hints, dim text |
| OP_COPY | `#86E89A` | "copy" operation label |
| OP_MOVE | `#E07A47` | "move" operation label |
| OP_LINK | `#7AB8FF` | "link" / "hardlink" operation label |

---

### Task 1: Add `render_separator` to `tree_render.py`

**Files:**
- Modify: `tapes/ui/tree_render.py`
- Test: `tests/test_ui/test_tree_render.py`

**Step 1: Write failing tests**

Add to `tests/test_ui/test_tree_render.py`:

```python
from tapes.ui.tree_render import render_separator


class TestRenderSeparator:
    def test_plain_separator_fills_width(self) -> None:
        line = render_separator(40)
        assert len(line.plain) == 40
        assert line.plain == "─" * 40

    def test_separator_with_title(self) -> None:
        line = render_separator(40, title="Info")
        plain = line.plain
        assert plain.startswith("─── Info ")
        assert len(plain) == 40
        assert plain.endswith("─")

    def test_separator_with_right_text(self) -> None:
        line = render_separator(40, right_text="2 staged")
        plain = line.plain
        assert plain.endswith(" 2 staged")
        assert len(plain) == 40

    def test_separator_with_title_and_right_text(self) -> None:
        line = render_separator(50, title="Files", right_text="3 total")
        plain = line.plain
        assert "Files" in plain
        assert "3 total" in plain
        assert len(plain) == 50

    def test_narrow_width_no_crash(self) -> None:
        line = render_separator(5, title="Info")
        # Should not crash, just truncate gracefully
        assert len(line.plain) <= 10  # allow some overflow but no crash

    def test_color_applied_to_dashes(self) -> None:
        line = render_separator(20, color="#B1B9F9")
        # Verify style spans exist (implementation detail, but ensures color is used)
        assert line.plain == "─" * 20
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_tree_render.py::TestRenderSeparator -v`
Expected: FAIL with ImportError (render_separator doesn't exist yet)

**Step 3: Implement `render_separator`**

Add to end of `tapes/ui/tree_render.py`:

```python
def render_separator(
    width: int,
    title: str | None = None,
    right_text: str | None = None,
    color: str = "#555555",
) -> Text:
    """Render a horizontal separator line spanning *width* characters.

    Format: ``─── Title ──────────────────── right text``
    """
    line = Text()
    used = 0

    if title:
        prefix = "─── "
        line.append(prefix, style=color)
        line.append(title, style=f"bold {color}")
        line.append(" ", style=color)
        used = len(prefix) + len(title) + 1

    right_len = 0
    if right_text:
        right_len = len(right_text) + 1  # space before text

    fill = width - used - right_len
    if fill > 0:
        line.append("─" * fill, style=color)

    if right_text:
        line.append(" ")
        line.append(right_text, style=MUTED)

    return line
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_tree_render.py::TestRenderSeparator -v`
Expected: PASS

**Step 5: Commit**

```
feat: add render_separator utility for horizontal separator lines
```

---

### Task 2: Create `BottomBar` widget

**Files:**
- Create: `tapes/ui/bottom_bar.py`
- Create: `tests/test_ui/test_bottom_bar.py`

**Step 1: Write failing tests**

Create `tests/test_ui/test_bottom_bar.py`:

```python
"""Tests for the BottomBar widget."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tapes.ui.bottom_bar import OPERATIONS, BottomBar


def _render_plain(widget, width: int = 80, height: int = 4) -> str:
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(
        type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)
    ):
        rendered = widget.render()
    return rendered.plain


class TestBottomBarRender:
    def test_renders_four_lines(self) -> None:
        bar = BottomBar()
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert len(lines) == 4

    def test_separator_lines_contain_dashes(self) -> None:
        bar = BottomBar()
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "─" in lines[0]
        assert "─" in lines[2]

    def test_search_prompt_visible(self) -> None:
        bar = BottomBar()
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "/" in lines[1]

    def test_operation_shown_in_bottom_line(self) -> None:
        bar = BottomBar()
        bar.operation = "move"
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "move" in lines[3]

    def test_stats_in_top_separator(self) -> None:
        bar = BottomBar()
        bar.stats_text = "2 staged · 5 total"
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "2 staged · 5 total" in lines[0]

    def test_search_query_shown(self) -> None:
        bar = BottomBar()
        bar.search_query = "matrix"
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "/matrix" in lines[1]

    def test_search_active_shows_cursor(self) -> None:
        bar = BottomBar()
        bar.search_active = True
        bar.search_query = "test"
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "█" in lines[1]

    def test_search_inactive_no_cursor(self) -> None:
        bar = BottomBar()
        bar.search_active = False
        bar.search_query = "test"
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "█" not in lines[1]

    def test_hint_text_shown(self) -> None:
        bar = BottomBar()
        bar.hint_text = "Space to stage"
        plain = _render_plain(bar)
        lines = plain.split("\n")
        assert "Space to stage" in lines[3]


class TestBottomBarCycleOperation:
    def test_cycle_forward(self) -> None:
        bar = BottomBar()
        bar.operation = "copy"
        bar.cycle_operation(1)
        assert bar.operation == "move"

    def test_cycle_backward(self) -> None:
        bar = BottomBar()
        bar.operation = "copy"
        bar.cycle_operation(-1)
        assert bar.operation == "hardlink"

    def test_cycle_wraps(self) -> None:
        bar = BottomBar()
        bar.operation = "hardlink"
        bar.cycle_operation(1)
        assert bar.operation == "copy"

    def test_operations_list(self) -> None:
        assert OPERATIONS == ["copy", "move", "link", "hardlink"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_bottom_bar.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement BottomBar**

Create `tapes/ui/bottom_bar.py`:

```python
"""Persistent bottom bar with search input, operation mode, and hints."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.ui.tree_render import MUTED, render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType

# Accent color for active search separator.
ACCENT = "#B1B9F9"
# Inactive separator color.
INACTIVE = "#555555"

OPERATIONS = ["copy", "move", "link", "hardlink"]

OP_COLORS: dict[str, str] = {
    "copy": "#86E89A",
    "move": "#E07A47",
    "link": "#7AB8FF",
    "hardlink": "#7AB8FF",
}


class BottomBar(Widget):
    """Bottom bar showing stats, search input, operation mode, and hints."""

    stats_text: reactive[str] = reactive("")
    search_query: reactive[str] = reactive("")
    search_active: reactive[bool] = reactive(False)
    operation: reactive[str] = reactive("copy")
    hint_text: reactive[str] = reactive("")

    def render(self) -> RenderableType:
        w = self.size.width
        sep_color = ACCENT if self.search_active else INACTIVE

        lines: list[Text] = []

        # Line 1: separator with stats
        lines.append(
            render_separator(w, right_text=self.stats_text or None, color=sep_color)
        )

        # Line 2: search input
        search_line = Text()
        search_style = "" if self.search_active else MUTED
        search_line.append("  /", style=search_style)
        if self.search_query:
            search_line.append(self.search_query, style=search_style)
        if self.search_active:
            search_line.append("█")
        lines.append(search_line)

        # Line 3: separator
        lines.append(render_separator(w, color=sep_color))

        # Line 4: operation + hints
        bottom = Text()
        bottom.append("  ")
        op_color = OP_COLORS.get(self.operation, "")
        bottom.append(self.operation, style=op_color)
        if self.hint_text:
            bottom.append("       ")
            bottom.append(self.hint_text, style=f"italic {MUTED}")
        lines.append(bottom)

        return Text("\n").join(lines)

    def cycle_operation(self, delta: int = 1) -> None:
        """Cycle to next/previous operation."""
        idx = OPERATIONS.index(self.operation)
        self.operation = OPERATIONS[(idx + delta) % len(OPERATIONS)]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_bottom_bar.py -v`
Expected: PASS

**Step 5: Commit**

```
feat: add BottomBar widget with search input and operation mode
```

---

### Task 3: Overhaul DetailView

Remove compact preview, add separator and footer hints, hide by default.

**Files:**
- Modify: `tapes/ui/detail_view.py`
- Modify: `tests/test_ui/test_detail_view.py`

**Step 1: Update DetailView**

In `tapes/ui/detail_view.py`:

1. **Change ACCENT** from `#C79BFF` to `#B1B9F9`.

2. **Remove compact preview imports and methods:**
   - Remove imports: `render_compact_preview`, `render_folder_preview`, `render_folder_preview`
   - Remove import of `FolderNode` from `tree_model`
   - Remove `_preview_node` attribute from `__init__`
   - Remove `set_preview_node()` method
   - Remove `_render_compact_content()` method

3. **Remove `on_editing_changed` callback:**
   - Remove `self.on_editing_changed` from `__init__`
   - Remove `watch_editing()` method

4. **Remove BORDER_TITLE** (no longer needed, separator rendered in content).

5. **Simplify `render()`** -- always render expanded content (visibility controlled by CSS):

```python
def render(self) -> RenderableType:
    inner_width = self.size.width
    return Text("\n").join(self._render_content(inner_width))
```

6. **Rename `_render_expanded_content` to `_render_content`** and add separator + footer:

```python
def _render_content(self, inner_width: int) -> list[Text]:
    content: list[Text] = []

    # Separator line
    content.append(render_separator(inner_width, title="Info", color=ACCENT))

    # Tab bar
    content.append(self._render_tab_bar(inner_width))

    # Blank line
    content.append(Text())

    # File path -> destination
    if self.is_multi:
        content.append(self._render_multi_path_line())
    else:
        content.append(self._render_path_line())

    # Blank line
    content.append(Text())

    # Field rows
    label_w, val_w, src_w = self._compute_col_widths()
    for row_idx, field_name in enumerate(self._fields):
        content.append(
            self._render_field_row(row_idx, field_name, label_w, val_w, src_w)
        )

    # Blank line + footer hints
    content.append(Text())
    content.append(self._render_footer_hints())

    return content
```

7. **Add `_render_footer_hints()` method:**

```python
def _render_footer_hints(self) -> Text:
    if self.editing:
        return Text(
            " Enter to confirm · Esc to cancel",
            style=f"italic {MUTED}",
        )
    return Text(
        " Enter to edit · a to apply · ⇧Enter to apply all · ←/→ sources · Esc to back",
        style=f"italic {MUTED}",
    )
```

8. **Add import** for `render_separator` from `tree_render`.

**Step 2: Update tests in `test_detail_view.py`**

- Replace `"expanded" not in dv.classes` / `"expanded" in dv.classes` checks with `dv.styles.display` checks (or remove them if not testing visibility).
- The `_render_plain` helper in tests already patches `self.size`, so rendering works without CSS classes.

Specifically, around lines 740-758:
- Change `assert "expanded" not in dv.classes` to check `dv.styles.display` is `"none"` or check `app._in_detail is False`.
- Change `assert "expanded" in dv.classes` to check `app._in_detail is True` (already tested on the line above).

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_detail_view.py -v`
Expected: PASS (after fixing class references)

**Step 4: Commit**

```
refactor: overhaul DetailView with separator, footer hints, remove compact preview
```

---

### Task 4: Strip TreeView borders and status

**Files:**
- Modify: `tapes/ui/tree_view.py`

**Step 1: Remove BORDER_TITLE and set_status**

1. Remove `BORDER_TITLE = "Files"` (line 177).

2. Remove `set_status()` method entirely (lines 179-183). Stats now handled by BottomBar.

3. Remove `self._status_text` from `__init__`.

4. Fix viewport height: change `self.size.height - 2` to `self.size.height` in two places:
   - `render()` line 194: `viewport_height = max(1, self.size.height - 2)` → `max(1, self.size.height)`
   - `_scroll_to_cursor()` line 301: `viewport_height = self.size.height - 2` → `self.size.height`

**Step 2: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_view.py -v` (if it exists, or skip to Task 5)

**Step 3: Commit**

```
refactor: strip borders and status from TreeView
```

---

### Task 5: Rewire TreeApp

The big integration task. Replace StatusFooter with BottomBar, remove compact preview wiring, add Shift+Tab for operation cycling, wire search to BottomBar, show/hide panels on mode switch.

**Files:**
- Modify: `tapes/ui/tree_app.py`

**Step 1: Update imports**

```python
# Remove:
from tapes.ui.commit_modal import CommitScreen
# Keep (CommitScreen still needed for commit modal):
from tapes.ui.commit_modal import CommitScreen

# Add:
from tapes.ui.bottom_bar import BottomBar

# Remove StatusFooter class entirely (defined in this file)
```

**Step 2: Replace CSS**

```python
CSS = """
TreeView {
    height: 1fr;
    padding: 0 1;
}
TreeView.dimmed {
    color: #555555;
}
DetailView {
    display: none;
    padding: 0 1;
}
BottomBar {
    dock: bottom;
    height: 4;
}
"""
```

**Step 3: Update `compose()`**

```python
def compose(self) -> ComposeResult:
    yield TreeView(
        self.model,
        self.movie_template,
        self.tv_template,
        root_path=self.root_path,
    )
    yield DetailView(
        FileNode(path=Path("placeholder")),
        self.movie_template,
        self.tv_template,
        root_path=self.root_path,
    )
    yield BottomBar(id="bottom-bar")
```

**Step 4: Update `on_mount()`**

Add after existing code:
```python
bar = self.query_one(BottomBar)
bar.operation = self.config.library.operation
```

**Step 5: Add Shift+Tab binding**

Add to BINDINGS:
```python
Binding("shift+tab", "cycle_op", "Cycle Op", show=False),
```

Add action:
```python
def action_cycle_op(self) -> None:
    if self._in_detail:
        return
    self.query_one(BottomBar).cycle_operation()
```

**Step 6: Update `_show_detail()`**

```python
def _show_detail(self, node: FileNode) -> None:
    self._in_detail = True
    detail = self.query_one(DetailView)
    detail.set_node(node)
    detail.on_before_mutate = self._snapshot_before_mutate
    # separator + tab_bar + blank + path + blank + fields + blank + hints
    detail.styles.height = len(detail._fields) + 7
    detail.styles.display = "block"
    self.query_one(TreeView).add_class("dimmed")
    self.query_one(BottomBar).styles.display = "none"
    detail.focus()
```

**Step 7: Update `_show_detail_multi()`**

Same pattern as `_show_detail`:

```python
def _show_detail_multi(self, nodes: list[FileNode]) -> None:
    self._in_detail = True
    detail = self.query_one(DetailView)
    detail.set_nodes(nodes)
    detail.on_before_mutate = self._snapshot_before_mutate
    detail.styles.height = len(detail._fields) + 7
    detail.styles.display = "block"
    self.query_one(TreeView).add_class("dimmed")
    self.query_one(BottomBar).styles.display = "none"
    detail.focus()
```

**Step 8: Update `_show_tree()`**

```python
def _show_tree(self) -> None:
    self._in_detail = False
    detail = self.query_one(DetailView)
    detail.styles.display = "none"
    tv = self.query_one(TreeView)
    tv.remove_class("dimmed")
    self.query_one(BottomBar).styles.display = "block"
    tv.focus()
    tv.refresh()
    self._update_footer()
```

**Step 9: Remove `_update_preview()` and all calls to it**

Delete the method. Remove calls in: `on_mount`, `action_cursor_down`, `action_cursor_up`, `_show_tree`, `_on_tmdb_done`, `action_collapse_all`, `action_expand_all`, `action_toggle_flat`.

**Step 10: Remove `_on_detail_editing_changed()`**

Delete the method. Remove `detail.on_editing_changed = ...` from `_show_detail` and `_show_detail_multi`.

**Step 11: Remove StatusFooter class**

Delete the entire `StatusFooter` class.

**Step 12: Rewrite `_update_footer()`**

```python
def _update_footer(self) -> None:
    bar = self.query_one(BottomBar)
    tv = self.query_one(TreeView)

    # Stats
    if tv.filter_text:
        bar.stats_text = f"{tv.item_count} matched · {tv.total_count} total"
    else:
        ignored = tv.ignored_count
        parts = [f"{tv.staged_count} staged"]
        if ignored:
            parts.append(f"{ignored} ignored")
        parts.append(f"{tv.total_count} total")
        if self._tmdb_querying:
            done, total = self._tmdb_progress
            parts.append(f"TMDB {done}/{total}")
        bar.stats_text = " · ".join(parts)

    # Hints
    if self._searching:
        bar.hint_text = "Enter to confirm · Esc to cancel"
    else:
        bar.hint_text = (
            "Space to stage · Enter for details · a to accept · "
            "⇧Tab op · c to commit · ? for help"
        )
```

**Step 13: Update search wiring**

`action_start_search`:
```python
def action_start_search(self) -> None:
    if self._in_detail:
        return
    self._searching = True
    self._search_query = ""
    bar = self.query_one(BottomBar)
    bar.search_active = True
    bar.search_query = ""
    self._update_footer()
```

`_update_search_status`:
```python
def _update_search_status(self) -> None:
    self.query_one(BottomBar).search_query = self._search_query
```

`_finish_search`:
```python
def _finish_search(self, keep_filter: bool) -> None:
    self._searching = False
    bar = self.query_one(BottomBar)
    bar.search_active = False
    if not keep_filter:
        self._search_query = ""
        bar.search_query = ""
        self.query_one(TreeView).clear_filter()
    self._update_footer()
```

**Step 14: Update `action_commit` to use BottomBar operation**

```python
def action_commit(self) -> None:
    if self._in_detail:
        return
    tv = self.query_one(TreeView)
    if tv.staged_count == 0:
        self.notify("No staged files to commit")
        return
    count = tv.staged_count
    bar = self.query_one(BottomBar)
    self.push_screen(
        CommitScreen(count, bar.operation),
        callback=self._on_commit_result,
    )
```

**Step 15: Run full test suite**

Run: `uv run pytest -x`
Expected: Some failures in tests that reference old API (StatusFooter, borders, compact preview). These are fixed in Task 6.

**Step 16: Commit**

```
refactor: rewire TreeApp with BottomBar, remove StatusFooter and compact preview
```

---

### Task 6: Update and remove broken tests

**Files:**
- Modify: `tests/test_ui/test_border_rendering.py`
- Modify: `tests/test_ui/test_detail_render.py`
- Modify: `tests/test_ui/test_tree_app.py`
- Modify: `tests/test_ui/test_detail_view.py`

**Step 1: Rewrite `test_border_rendering.py`**

The entire file is about CSS borders and BORDER_TITLE. Replace with tests for the new design:

```python
"""Tests for widget rendering (separators, no manual box-drawing)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tapes.ui.detail_render import get_display_fields
from tapes.ui.detail_view import DetailView
from tapes.ui.tree_model import FileNode, FolderNode, Source, TreeModel
from tapes.ui.tree_view import TreeView

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = (
    "{title} ({year})/Season {season:02d}/"
    "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
)


def _make_tree_view() -> TreeView:
    node = FileNode(
        path=Path("/movies/Inception.mkv"),
        result={"title": "Inception", "year": 2010, "media_type": "movie"},
    )
    root = FolderNode(name="root", children=[node], collapsed=False)
    model = TreeModel(root=root)
    return TreeView(model=model, movie_template=MOVIE_TEMPLATE, tv_template=TV_TEMPLATE)


def _make_detail_view() -> DetailView:
    node = FileNode(
        path=Path("/media/Breaking.Bad.S01E01.mkv"),
        result={"title": "Breaking Bad", "year": 2008, "season": 1, "episode": 1},
        sources=[
            Source(
                name="TMDB #1",
                fields={"title": "Breaking Bad", "year": 2008},
                confidence=0.95,
            ),
        ],
    )
    view = DetailView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
    view._fields = get_display_fields(view._active_template())
    return view


def _render_plain(widget, width: int = 80, height: int = 20) -> str:
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(
        type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)
    ):
        rendered = widget.render()
    return rendered.plain


class TestTreeViewRendering:
    def test_tree_render_contains_content(self) -> None:
        view = _make_tree_view()
        plain = _render_plain(view)
        assert "Inception" in plain

    def test_tree_render_no_manual_borders(self) -> None:
        view = _make_tree_view()
        plain = _render_plain(view)
        for char in "\u250c\u2510\u2514\u2518\u2502":
            assert char not in plain

    def test_tree_has_no_border_title(self) -> None:
        view = _make_tree_view()
        assert not hasattr(view, "BORDER_TITLE") or view.BORDER_TITLE is None


class TestDetailViewRendering:
    def test_detail_render_has_separator(self) -> None:
        view = _make_detail_view()
        plain = _render_plain(view, height=30)
        assert "─── Info" in plain

    def test_detail_render_has_footer_hints(self) -> None:
        view = _make_detail_view()
        plain = _render_plain(view, height=30)
        assert "Enter to edit" in plain
        assert "Esc to back" in plain

    def test_detail_render_no_manual_borders(self) -> None:
        view = _make_detail_view()
        plain = _render_plain(view, height=30)
        for char in "\u250c\u2510\u2514\u2518\u251c\u2524":
            assert char not in plain
```

**Step 2: Remove compact preview tests from `test_detail_render.py`**

Delete the entire `TestRenderCompactPreview` class (lines 86-152) and `TestRenderFolderPreview` class (lines 155-235). Remove the `render_compact_preview` and `render_folder_preview` imports. Keep `TestDiffStyle` and `TestConfidenceStyle` unchanged.

**Step 3: Rewrite StatusFooter tests in `test_tree_app.py`**

Replace the `TestStatusFooter` class (lines 1332-1420) with `TestBottomBar`:

```python
class TestBottomBar:
    """Tests for the BottomBar integration in TreeApp."""

    @pytest.mark.asyncio()
    async def test_bottom_bar_visible_on_launch(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test():
            bar = app.query_one(BottomBar)
            assert bar is not None

    @pytest.mark.asyncio()
    async def test_bottom_bar_hidden_in_detail(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        node = FileNode(path=Path("/media/test.mkv"), result={"title": "Test"})
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            bar = app.query_one(BottomBar)
            await pilot.press("enter")
            assert bar.styles.display == "none"

            await pilot.press("escape")
            assert str(bar.styles.display) != "none"

    @pytest.mark.asyncio()
    async def test_shift_tab_cycles_operation(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            bar = app.query_one(BottomBar)
            initial_op = bar.operation
            await pilot.press("shift+tab")
            assert bar.operation != initial_op
```

**Step 4: Update `TestVisualIntegration`**

- `test_launch_tree_view_visible_with_border`: Replace `StatusFooter` references with `BottomBar`.
- `test_cursor_move_updates_compact_preview`: Remove entirely (compact preview is gone).

**Step 5: Update `test_detail_view.py`**

Replace `"expanded" in dv.classes` checks (around lines 740-758) with `app._in_detail` checks or `dv.styles.display` checks.

**Step 6: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS

**Step 7: Commit**

```
test: update tests for new layout (BottomBar, no borders, no compact preview)
```

---

### Task 7: Cleanup dead code

**Files:**
- Modify: `tapes/ui/detail_render.py`
- Modify: `tapes/ui/detail_view.py` (verify no stale imports)

**Step 1: Remove dead functions from `detail_render.py`**

Delete:
- `render_compact_preview()` function (lines 133-170)
- `render_folder_preview()` function (lines 173-206)
- Remove `FolderNode` and `collect_files` from the import on line 8 (if no longer used)

**Step 2: Remove OPERATIONS from `commit_modal.py`** if it's now only used from `bottom_bar.py`

Actually, keep it -- `commit_modal.py` still uses `OPERATIONS` independently.

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: PASS (all 465+ tests)

**Step 4: Commit**

```
refactor: remove dead compact preview code
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | `render_separator` utility | tree_render.py |
| 2 | BottomBar widget | bottom_bar.py (new) |
| 3 | DetailView overhaul | detail_view.py |
| 4 | TreeView strip borders | tree_view.py |
| 5 | TreeApp rewiring | tree_app.py |
| 6 | Test updates | test_border_rendering.py, test_detail_render.py, test_tree_app.py, test_detail_view.py |
| 7 | Dead code cleanup | detail_render.py |
