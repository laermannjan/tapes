# Visual Fixes and Commit View Implementation Plan

Status: **completed** (merged to main 2026-03-08)

**Goal:** Fix visual issues (dimming, cursor color, column layout, tab wrapping), remove `a` binding, add op hint to bottom bar, pad stats text, and replace CommitScreen modal with an inline CommitView widget.

**Architecture:** Quick fixes are isolated CSS/constant/logic changes. The CommitView is a new Widget rendered like DetailView (pop up from bottom, dim tree, hide BottomBar, embed op mode). CommitScreen modal and commit_modal.py are deleted.

**Tech Stack:** Textual 8, Rich Text, Python 3.11+

---

### Task 1: Quick visual fixes

Six small fixes in one commit.

**Files:**
- Modify: `tapes/ui/tree_app.py`
- Modify: `tapes/ui/tree_render.py`
- Modify: `tapes/ui/detail_view.py`
- Modify: `tapes/ui/bottom_bar.py`

**Step 1: Fix dimming opacity**

In `tapes/ui/tree_app.py` CSS string, change:
```css
TreeView.dimmed {
    opacity: 0.4;
}
```
To:
```css
TreeView.dimmed {
    opacity: 0.65;
}
```

**Step 2: Fix cursor highlight color**

In `tapes/ui/tree_render.py`, change:
```python
CURSOR_BG = "on #36345a"
```
To:
```python
CURSOR_BG = "on #373737"
```

**Step 3: Fix tab wrapping in cycle_source**

In `tapes/ui/detail_view.py`, change `cycle_source`:
```python
def cycle_source(self, delta: int) -> None:
    """Cycle through source tabs."""
    if self.editing:
        return
    sources = self.node.sources
    if not sources:
        return
    self.source_index = (self.source_index + delta) % len(sources)
```

**Step 4: Remove `a accept` from tree hints and remove `a` binding**

In `tapes/ui/tree_app.py`, remove the binding:
```python
Binding("a", "accept_best", "Accept"),
```

Remove the entire `action_accept_best` method.

Remove the `accept_best_source` import from the `tree_model` import line.

Change `_update_footer` tree hints from:
```python
bar.hint_text = (
    "space stage · enter details · a accept · "
    "shift-tab op · c commit · ? help"
)
```
To:
```python
bar.hint_text = (
    "space stage · enter details · "
    "shift-tab op · c commit · ? help"
)
```

**Step 5: Add stats right-padding in render_separator**

In `tapes/ui/tree_render.py`, change `render_separator`. The `right_text` currently goes to the edge. Add 2-char padding:

Change:
```python
    right_len = 0
    if right_text:
        right_len = len(right_text) + 1  # space before text
```
To:
```python
    right_len = 0
    if right_text:
        right_len = len(right_text) + 3  # space before + 2 right padding
```

And change the right_text rendering at the end:
```python
    if right_text:
        line.append(" ")
        line.append(right_text, style=MUTED)
```
To:
```python
    if right_text:
        line.append(" ")
        line.append(right_text, style=MUTED)
        line.append("  ")
```

**Step 6: Add `(shift-tab)` hint next to op mode in BottomBar**

In `tapes/ui/bottom_bar.py`, in the render method, after the operation label, add the hint. Change the bottom line section:

```python
        # Line 4: operation + hints
        bottom = Text()
        bottom.append("  ")
        op_color = OP_COLORS.get(self.operation, "")
        bottom.append(self.operation, style=op_color)
        bottom.append("  ")
        bottom.append("(shift-tab)", style=MUTED)
        if self.hint_text:
            bottom.append("       ")
            bottom.append(self.hint_text, style=f"italic {MUTED}")
        lines.append(bottom)
```

**Step 7: Run tests**

Run: `uv run pytest -x`
Expected: Some tests may fail due to `accept_best` removal and text changes. Fix any that reference removed `a` binding, `accept_best_source`, or changed hint text.

Specific tests to check/update:
- `tests/test_ui/test_tree_app.py`: any test that presses `a` or tests `action_accept_best`
- `tests/test_ui/test_help_overlay.py`: the `a` key row
- `tests/test_ui/test_tree_render.py`: `TestRenderSeparator` tests may need updating for the 2-char padding

**Step 8: Update help overlay**

In `tapes/ui/help_overlay.py`, remove the `a` line from `file_keys`:
```python
("a", "accept best TMDB match"),
```

**Step 9: Run tests again**

Run: `uv run pytest -x`
Expected: PASS

**Step 10: Commit**

```
fix: visual fixes (dimming, cursor color, tab wrap, column padding, remove a binding)
```

---

### Task 2: Fix source column position in detail view

The source column is pushed too far right because `_compute_col_widths` gives all spare space to the value column.

**Files:**
- Modify: `tapes/ui/detail_view.py`

**Step 1: Rewrite `_compute_col_widths`**

Replace the method with:

```python
def _compute_col_widths(self) -> tuple[int, int, int]:
    """Compute auto-sized column widths: (label_w, value_w, source_w).

    Label and value columns are measured by content. The source column
    starts after a gap. The label+gap+value portion is capped at 50%
    of the widget width so the source column stays visible.
    """
    shared = self._shared_result()
    sources = self.node.sources
    gap = len(COL_GAP)
    inner = self.size.width

    # Measure label column
    label_w = max((len(f) for f in self.fields), default=6) + 2  # 2 left pad

    # Measure value column by content
    val_w = 6  # minimum
    for f in self.fields:
        v = display_val(shared.get(f))
        val_w = max(val_w, len(v))

    # Measure source column
    src_w = 0
    if sources and self.source_index < len(sources):
        src = sources[self.source_index]
        for f in self.fields:
            v = display_val(src.fields.get(f))
            src_w = max(src_w, len(v))
        src_w = max(src_w, 6)  # minimum

    # Cap label+gap+value at 50% of width when source column exists
    if src_w > 0:
        max_left = inner // 2
        left_used = label_w + gap + val_w
        if left_used > max_left:
            val_w = max(6, max_left - label_w - gap)

    return (label_w, val_w, src_w)
```

**Step 2: Run tests**

Run: `uv run pytest -x`
Expected: PASS

**Step 3: Commit**

```
fix: cap detail view source column at 50% width
```

---

### Task 3: Create CommitView widget

A new widget that replaces the modal. Renders inline like DetailView.

**Files:**
- Create: `tapes/ui/commit_view.py`
- Create: `tests/test_ui/test_commit_view.py`

**Step 1: Write tests**

Create `tests/test_ui/test_commit_view.py`:

```python
"""Tests for the inline commit view."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tapes.ui.commit_view import CommitView, categorize_staged
from tapes.ui.tree_model import FileNode


def _render_plain(widget, width: int = 80, height: int = 20) -> str:
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(
        type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)
    ):
        rendered = widget.render()
    return rendered.plain


class TestCategorizeStaged:
    def test_movies(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.mkv"), result={"media_type": "movie"}),
        ]
        cats = categorize_staged(files)
        assert cats["movies"] == 2

    def test_episodes(self) -> None:
        files = [
            FileNode(
                path=Path("/a.mkv"),
                result={"media_type": "episode", "title": "Show", "season": 1},
            ),
            FileNode(
                path=Path("/b.mkv"),
                result={"media_type": "episode", "title": "Show", "season": 2},
            ),
            FileNode(
                path=Path("/c.mkv"),
                result={"media_type": "episode", "title": "Other", "season": 1},
            ),
        ]
        cats = categorize_staged(files)
        assert cats["episodes"] == 3
        assert cats["shows"] == 2
        assert cats["seasons"] == 3

    def test_subtitles(self) -> None:
        files = [
            FileNode(path=Path("/a.srt"), result={}),
            FileNode(path=Path("/b.ass"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["subtitles"] == 2

    def test_sidecars(self) -> None:
        files = [
            FileNode(path=Path("/a.nfo"), result={}),
            FileNode(path=Path("/b.xml"), result={}),
            FileNode(path=Path("/c.jpg"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["sidecars"] == 3

    def test_other(self) -> None:
        files = [
            FileNode(path=Path("/a.txt"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["other"] == 1

    def test_total(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.srt"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["total"] == 2


class TestCommitViewRender:
    def test_renders_separator(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        plain = _render_plain(view)
        assert "Commit" in plain

    def test_renders_stats(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.mkv"), result={"media_type": "movie"}),
        ]
        view = CommitView(files, "copy")
        plain = _render_plain(view)
        assert "2 movies" in plain

    def test_renders_operation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "move")
        plain = _render_plain(view)
        assert "move" in plain

    def test_renders_hints(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        plain = _render_plain(view)
        assert "enter confirm" in plain
        assert "esc cancel" in plain

    def test_cycle_operation_wraps(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "hardlink")
        view.cycle_operation(1)
        assert view.operation == "copy"


class TestCommitViewHeight:
    def test_height_calculation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        # separator + blank + stats_line_1 + stats_line_2 + blank + total + blank + separator + op_line
        # Minimum ~9 lines, depends on categories present
        assert view.computed_height >= 7
```

**Step 2: Implement `tapes/ui/commit_view.py`**

```python
"""Inline commit confirmation view with file stats and operation selection."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE
from tapes.ui.bottom_bar import OPERATIONS, OP_COLORS
from tapes.ui.tree_model import FileNode
from tapes.ui.tree_render import MUTED, render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType

ACCENT = "#B1B9F9"

SUBTITLE_EXTS = frozenset({".srt", ".sub", ".ass", ".ssa", ".idx"})
SIDECAR_EXTS = frozenset({".nfo", ".xml", ".jpg", ".png"})


def categorize_staged(files: list[FileNode]) -> dict[str, int]:
    """Categorize staged files and return counts."""
    movies = 0
    episodes = 0
    subtitles = 0
    sidecars = 0
    other = 0
    shows: set[str] = set()
    seasons: set[tuple[str, Any]] = set()

    for f in files:
        ext = f.path.suffix.lower()
        media_type = f.result.get(MEDIA_TYPE)

        if media_type == MEDIA_TYPE_MOVIE:
            movies += 1
        elif media_type == MEDIA_TYPE_EPISODE:
            episodes += 1
            title = f.result.get("title", "")
            season = f.result.get("season")
            if title:
                shows.add(title)
            if title and season is not None:
                seasons.add((title, season))
        elif ext in SUBTITLE_EXTS:
            subtitles += 1
        elif ext in SIDECAR_EXTS:
            sidecars += 1
        else:
            other += 1

    return {
        "movies": movies,
        "episodes": episodes,
        "shows": len(shows),
        "seasons": len(seasons),
        "subtitles": subtitles,
        "sidecars": sidecars,
        "other": other,
        "total": len(files),
    }


class CommitView(Widget):
    """Inline commit view showing staged file stats and operation selection."""

    can_focus = True

    operation: reactive[str] = reactive("copy")

    def __init__(self, files: list[FileNode], operation: str) -> None:
        super().__init__()
        self._files = files
        self.operation = operation
        self._categories = categorize_staged(files)

    @property
    def computed_height(self) -> int:
        """Compute the height needed for this view."""
        # separator + blank + stats lines + blank + total + blank + separator + op line
        lines = 4  # separator + blank + total-blank + separator + op
        cats = self._categories
        if cats["movies"] or cats["subtitles"] or cats["sidecars"] or cats["other"]:
            lines += 1
        if cats["episodes"]:
            lines += 1
        lines += 3  # blank + total + blank
        return lines

    def render(self) -> RenderableType:
        w = self.size.width
        return Text("\n").join(self._build_content(w))

    def _build_content(self, width: int) -> list[Text]:
        content: list[Text] = []
        cats = self._categories

        # Separator
        content.append(render_separator(width, title="Commit", color=ACCENT))

        # Blank
        content.append(Text())

        # Stats line 1: movies · subtitles · sidecars · other
        line1_parts: list[str] = []
        if cats["movies"]:
            n = cats["movies"]
            line1_parts.append(f"{n} {'movie' if n == 1 else 'movies'}")
        if cats["subtitles"]:
            n = cats["subtitles"]
            line1_parts.append(f"{n} {'subtitle' if n == 1 else 'subtitles'}")
        if cats["sidecars"]:
            n = cats["sidecars"]
            line1_parts.append(f"{n} {'sidecar' if n == 1 else 'sidecars'}")
        if cats["other"]:
            n = cats["other"]
            line1_parts.append(f"{n} other")
        if line1_parts:
            content.append(Text(f"  {' \u00b7 '.join(line1_parts)}"))

        # Stats line 2: shows · seasons · episodes
        line2_parts: list[str] = []
        if cats["shows"]:
            n = cats["shows"]
            line2_parts.append(f"{n} {'show' if n == 1 else 'shows'}")
        if cats["seasons"]:
            n = cats["seasons"]
            line2_parts.append(f"{n} {'season' if n == 1 else 'seasons'}")
        if cats["episodes"]:
            n = cats["episodes"]
            line2_parts.append(f"{n} {'episode' if n == 1 else 'episodes'}")
        if line2_parts:
            content.append(Text(f"  {' \u00b7 '.join(line2_parts)}"))

        # Blank + total
        content.append(Text())
        total = cats["total"]
        content.append(Text(f"  {total} {'file' if total == 1 else 'files'} total"))

        # Blank
        content.append(Text())

        # Bottom separator
        content.append(render_separator(width, color=ACCENT))

        # Operation + hints line (mirrors BottomBar layout)
        bottom = Text()
        bottom.append("  ")
        op_color = OP_COLORS.get(self.operation, "")
        bottom.append(self.operation, style=op_color)
        bottom.append("  ")
        bottom.append("(shift-tab)", style=MUTED)
        bottom.append("       ")
        bottom.append("enter confirm \u00b7 esc cancel", style=f"italic {MUTED}")
        content.append(bottom)

        return content

    def cycle_operation(self, delta: int = 1) -> None:
        """Cycle to next/previous operation."""
        idx = OPERATIONS.index(self.operation)
        self.operation = OPERATIONS[(idx + delta) % len(OPERATIONS)]
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_commit_view.py -v`
Expected: PASS

**Step 4: Commit**

```
feat: add inline CommitView widget with file categorization
```

---

### Task 4: Wire CommitView into TreeApp, remove CommitScreen

**Files:**
- Modify: `tapes/ui/tree_app.py`
- Delete: `tapes/ui/commit_modal.py`
- Delete: `tests/test_ui/test_commit_modal.py`
- Modify: `tests/test_ui/test_tree_app.py`

**Step 1: Update TreeApp imports**

Replace:
```python
from tapes.ui.commit_modal import CommitScreen
```
With:
```python
from tapes.ui.commit_view import CommitView
```

**Step 2: Add `_in_commit` state to `__init__`**

```python
self._in_commit = False
```

**Step 3: Add CSS for CommitView**

Add to the CSS string:
```css
CommitView {
    display: none;
    padding: 0 1;
}
```

**Step 4: Add CommitView to `compose()`**

After the DetailView yield, before BottomBar:
```python
yield CommitView([], "copy", id="commit-view")
```

Update CommitView `__init__` to accept optional `id`:
Actually, `Widget.__init__` already accepts `id` via `**kwargs` -- but our `CommitView.__init__` overrides it. Update `CommitView.__init__` to pass through kwargs:

```python
def __init__(self, files: list[FileNode], operation: str, **kwargs: Any) -> None:
    super().__init__(**kwargs)
    ...
```

Wait, `Any` is already imported in commit_view.py in TYPE_CHECKING. Move it to runtime import or just use `id` parameter:

```python
def __init__(self, files: list[FileNode], operation: str, *, id: str | None = None) -> None:
    super().__init__(id=id)
    ...
```

**Step 5: Add `_show_commit` and `_hide_commit` methods**

```python
def _show_commit(self) -> None:
    """Show the commit confirmation view."""
    self._in_commit = True
    staged = [f for f in self.model.all_files() if f.staged]
    bar = self.query_one(BottomBar)
    cv = self.query_one(CommitView)
    cv._files = staged
    cv._categories = categorize_staged(staged)
    cv.operation = bar.operation
    cv.styles.height = cv.computed_height
    cv.styles.display = "block"
    self.query_one(TreeView).add_class("dimmed")
    bar.styles.display = "none"
    cv.focus()

def _hide_commit(self) -> None:
    """Hide the commit view and return to tree."""
    self._in_commit = False
    cv = self.query_one(CommitView)
    cv.styles.display = "none"
    tv = self.query_one(TreeView)
    tv.remove_class("dimmed")
    self.query_one(BottomBar).styles.display = "block"
    tv.focus()
    tv.refresh()
    self._update_footer()
```

Add import at top:
```python
from tapes.ui.commit_view import CommitView, categorize_staged
```

**Step 6: Rewrite `action_commit`**

```python
def action_commit(self) -> None:
    if self._in_detail:
        self._confirm_detail()
        return
    if self._in_commit:
        # Enter confirms
        cv = self.query_one(CommitView)
        self._hide_commit()
        self._do_commit(cv.operation)
        return
    tv = self.query_one(TreeView)
    if tv.staged_count == 0:
        self.notify("No staged files to commit")
        return
    self._show_commit()
```

**Step 7: Update `action_cancel` to handle commit view**

Add after the `_searching` check and before the `_in_detail` check:

```python
if self._in_commit:
    self._hide_commit()
    return
```

**Step 8: Update `on_key` for shift+tab in commit view**

Change the shift+tab intercept condition from:
```python
if event.key == "shift+tab" and not self._in_detail and not self._searching:
    self.action_cycle_op()
```
To:
```python
if event.key == "shift+tab" and not self._in_detail and not self._searching:
    if self._in_commit:
        self.query_one(CommitView).cycle_operation()
    else:
        self.query_one(BottomBar).cycle_operation()
    event.prevent_default()
    event.stop()
    return
```

**Step 9: Update `action_toggle_or_enter` for commit view**

Add at the top of `action_toggle_or_enter`:
```python
if self._in_commit:
    cv = self.query_one(CommitView)
    self._hide_commit()
    self._do_commit(cv.operation)
    return
```

Wait, actually `enter` is already bound to `action_toggle_or_enter`. But `c` triggers `action_commit`. Both should confirm in commit mode. Let me handle `enter` in commit mode within `action_toggle_or_enter`:

Actually, it's cleaner to just handle it in `action_toggle_or_enter`:
```python
def action_toggle_or_enter(self) -> None:
    if self._in_commit:
        cv = self.query_one(CommitView)
        self._hide_commit()
        self._do_commit(cv.operation)
        return
    if self._in_detail:
        ...
```

And also in `action_commit`, the `_in_commit` branch can just do the same:
```python
def action_commit(self) -> None:
    if self._in_detail:
        self._confirm_detail()
        return
    if self._in_commit:
        cv = self.query_one(CommitView)
        self._hide_commit()
        self._do_commit(cv.operation)
        return
    tv = self.query_one(TreeView)
    if tv.staged_count == 0:
        self.notify("No staged files to commit")
        return
    self._show_commit()
```

**Step 10: Guard other actions during commit mode**

In `action_cursor_down`, `action_cursor_up`, `action_cursor_left`, `action_cursor_right`, `action_toggle_staged`, `action_range_select`, `action_toggle_ignored`, `action_start_search`, `action_collapse_all`, `action_expand_all`, `action_toggle_flat`, `action_refresh_query`, `action_clear_field`, `action_reset_guessit`, `action_apply_all_clear`:

Add at the top of each:
```python
if self._in_commit:
    return
```

For brevity, this can be done by adding the guard to any action that shouldn't work during commit view. The key ones: all tree/detail navigation and mutation actions. The only actions that should work during commit: `cancel` (esc), `commit`/`toggle_or_enter` (enter/c), `toggle_help` (?).

**Step 11: Remove `_on_commit_result` callback**

Delete the method -- no longer needed (was the CommitScreen callback).

**Step 12: Delete `tapes/ui/commit_modal.py`**

Remove the file entirely.

**Step 13: Delete `tests/test_ui/test_commit_modal.py`**

Remove the file entirely.

**Step 14: Update tests in `tests/test_ui/test_tree_app.py`**

Find and update/remove any tests that reference `CommitScreen`, `commit_modal`, or push_screen for commit. Replace with tests for the new inline commit view:

```python
class TestCommitView:
    """Tests for the inline commit view in TreeApp."""

    @pytest.mark.asyncio()
    async def test_c_shows_commit_view(self) -> None:
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test"}, staged=True)
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert app._in_commit

    @pytest.mark.asyncio()
    async def test_esc_cancels_commit(self) -> None:
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test"}, staged=True)
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert app._in_commit
            await pilot.press("escape")
            assert not app._in_commit

    @pytest.mark.asyncio()
    async def test_no_commit_with_zero_staged(self) -> None:
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test"})
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert not app._in_commit
```

**Step 15: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS

**Step 16: Commit**

```
feat: replace commit modal with inline CommitView
```

---

## Summary

| Task | What | Key files |
|------|------|-----------|
| 1 | Quick fixes (dimming, cursor, tab, `a` removal, padding, op hint) | tree_app.py, tree_render.py, detail_view.py, bottom_bar.py, help_overlay.py |
| 2 | Source column cap at 50% | detail_view.py |
| 3 | Create CommitView widget | commit_view.py (new) |
| 4 | Wire CommitView, delete CommitScreen | tree_app.py, commit_modal.py (delete) |
