# Keybinding Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Streamline the keyboard workflow so common actions use universal keys (tab/enter/esc/space) and reduce random letter keymaps.

**Architecture:** Six tasks working through the codebase bottom-up: staging gate in the model/render layer, tree view keybinding changes, detail view column-focus model, commit view entry via tab, help overlay update, and test updates. Each task is self-contained with its own tests.

**Tech Stack:** Python 3.11+, Textual 8 (TUI framework), Rich (rendering), pytest, Textual Pilot (async app testing)

**Design doc:** `docs/plans/2026-03-09-keybinding-redesign-design.md`

---

### Task 1: Staging gate and ready-to-stage indicator

Files with incomplete template metadata cannot be staged. Show `☐` for
ready-to-stage files, `✓` for staged, nothing for incomplete.

**Files:**
- Modify: `tapes/ui/tree_render.py:287-291` (staging indicator)
- Modify: `tapes/tree_model.py:57-59` (toggle_staged)
- Modify: `tapes/tree_model.py:87-95` (toggle_staged_recursive)
- Test: `tests/test_ui/test_tree_render.py`
- Test: `tests/test_ui/test_tree_model.py`

**Step 1: Write failing tests for the staging gate**

In `tests/test_ui/test_tree_model.py`, add:

```python
class TestStagingGate:
    def test_toggle_staged_blocked_when_not_ready(self) -> None:
        """toggle_staged does nothing when can_stage returns False."""
        node = FileNode(path=Path("movie.mkv"))
        node.result = {MEDIA_TYPE: "movie", TITLE: "Inception"}  # no year
        model = TreeModel(root=FolderNode(name="root", children=[node]))

        def can_stage(n: FileNode) -> bool:
            from tapes.ui.tree_render import can_fill_template
            return can_fill_template(n, n.result, MOVIE_TEMPLATE, TV_TEMPLATE)

        model.toggle_staged(node, can_stage=can_stage)
        assert node.staged is False

    def test_toggle_staged_allowed_when_ready(self) -> None:
        """toggle_staged works when can_stage returns True."""
        node = FileNode(path=Path("movie.mkv"))
        node.result = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        model = TreeModel(root=FolderNode(name="root", children=[node]))

        def can_stage(n: FileNode) -> bool:
            from tapes.ui.tree_render import can_fill_template
            return can_fill_template(n, n.result, MOVIE_TEMPLATE, TV_TEMPLATE)

        model.toggle_staged(node, can_stage=can_stage)
        assert node.staged is True

    def test_toggle_staged_unstage_always_allowed(self) -> None:
        """Unstaging is always allowed regardless of can_stage."""
        node = FileNode(path=Path("movie.mkv"))
        node.result = {MEDIA_TYPE: "movie", TITLE: "Inception"}  # incomplete
        node.staged = True  # force staged
        model = TreeModel(root=FolderNode(name="root", children=[node]))

        def can_stage(n: FileNode) -> bool:
            return False  # would block staging

        model.toggle_staged(node, can_stage=can_stage)
        assert node.staged is False  # unstaging still works

    def test_toggle_staged_recursive_skips_incomplete(self) -> None:
        """toggle_staged_recursive only stages files that pass can_stage."""
        complete = FileNode(path=Path("a.mkv"))
        complete.result = {MEDIA_TYPE: "movie", TITLE: "A", YEAR: 2020}
        incomplete = FileNode(path=Path("b.mkv"))
        incomplete.result = {MEDIA_TYPE: "movie", TITLE: "B"}  # no year
        folder = FolderNode(name="root", children=[complete, incomplete])
        model = TreeModel(root=folder)

        def can_stage(n: FileNode) -> bool:
            from tapes.ui.tree_render import can_fill_template
            return can_fill_template(n, n.result, MOVIE_TEMPLATE, TV_TEMPLATE)

        model.toggle_staged_recursive(folder, can_stage=can_stage)
        assert complete.staged is True
        assert incomplete.staged is False
```

Use these imports at the top of the new tests:
```python
from tapes.fields import MEDIA_TYPE, TITLE, YEAR
MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_tree_model.py::TestStagingGate -v`
Expected: FAIL (toggle_staged doesn't accept can_stage parameter)

**Step 3: Implement the staging gate in TreeModel**

In `tapes/tree_model.py`, change `toggle_staged` (line 57):

```python
def toggle_staged(
    self,
    node: FileNode,
    can_stage: Callable[[FileNode], bool] | None = None,
) -> None:
    """Toggle staged flag on a file node.

    If *can_stage* is provided and the node is not currently staged,
    staging is only allowed when ``can_stage(node)`` returns True.
    Unstaging is always allowed.
    """
    if node.staged:
        node.staged = False
    elif can_stage is None or can_stage(node):
        node.staged = True
```

Add `Callable` import at top of file:
```python
from collections.abc import Callable
```

Change `toggle_staged_recursive` (line 87):

```python
def toggle_staged_recursive(
    self,
    node: FolderNode,
    can_stage: Callable[[FileNode], bool] | None = None,
) -> None:
    """Toggle staged on all file descendants.

    If ALL are staged, unstage all. Otherwise stage only those
    that pass *can_stage* (if provided).
    """
    files = collect_files(node)
    if not files:
        return
    all_staged = all(f.staged for f in files)
    if all_staged:
        for f in files:
            f.staged = False
    else:
        for f in files:
            if not f.staged:
                if can_stage is None or can_stage(f):
                    f.staged = True
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_tree_model.py::TestStagingGate -v`
Expected: PASS

**Step 5: Write failing test for the ready-to-stage indicator**

In `tests/test_ui/test_tree_render.py`, add:

```python
class TestReadyToStageIndicator:
    def test_staged_file_shows_check(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.result = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        node.staged = True
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "\u2713" in row.plain  # ✓

    def test_ready_file_shows_hollow_square(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.result = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        node.staged = False
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "\u2610" in row.plain  # ☐

    def test_incomplete_file_shows_no_indicator(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.result = {MEDIA_TYPE: "movie", TITLE: "Inception"}  # no year
        node.staged = False
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "\u2713" not in row.plain
        assert "\u2610" not in row.plain
```

**Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_tree_render.py::TestReadyToStageIndicator -v`
Expected: FAIL (no `☐` rendered yet)

**Step 7: Implement the ready-to-stage indicator**

In `tapes/ui/tree_render.py`, change lines 287-291:

```python
# Staging indicator: ✓ staged, ☐ ready to stage, blank if incomplete
if node.staged:
    row.append("\u2713 ", style=STAGED_COLOR)
elif can_fill_template(node, node.result, movie_template, tv_template):
    row.append("\u2610 ", style=MUTED)
else:
    row.append("  ")
```

The `movie_template` and `tv_template` parameters are already available
in the `render_file_row` function signature.

**Step 8: Run all tests**

Run: `uv run pytest tests/test_ui/test_tree_render.py tests/test_ui/test_tree_model.py -v`
Expected: ALL PASS

**Step 9: Commit**

```bash
git add tapes/tree_model.py tapes/ui/tree_render.py tests/test_ui/test_tree_model.py tests/test_ui/test_tree_render.py
git commit -m "feat: add staging gate and ready-to-stage indicator"
```

---

### Task 2: Tree view keybinding changes

Rewire tree view keys: enter = stage/unstage (files) or select-all + detail
(folders), h/l = collapse/expand, tab = commit preview.

**Files:**
- Modify: `tapes/ui/tree_app.py:70-90` (BINDINGS)
- Modify: `tapes/ui/tree_app.py:384-394` (cursor_left/right actions)
- Modify: `tapes/ui/tree_app.py:396-401` (toggle_staged)
- Modify: `tapes/ui/tree_app.py:428-451` (toggle_or_enter)
- Modify: `tapes/ui/tree_app.py:496-510` (commit action)
- Modify: `tapes/ui/tree_view.py:101-113` (toggle_staged_at_cursor)
- Test: `tests/test_ui/test_tree_app.py`

**Step 1: Update BINDINGS list**

In `tapes/ui/tree_app.py`, replace the BINDINGS (lines 70-90):

```python
BINDINGS: ClassVar[list[Binding]] = [
    Binding("j,down", "cursor_down", "Down"),
    Binding("k,up", "cursor_up", "Up"),
    Binding("enter", "primary_action", "Stage/Enter"),
    Binding("space", "toggle_staged", "Stage"),
    Binding("v", "range_select", "Range Select"),
    Binding("escape", "cancel", "Cancel"),
    Binding("x", "toggle_ignored", "Ignore"),
    Binding("e", "start_edit", "Edit", show=False),
    Binding("r", "refresh_query", "Refresh"),
    Binding("grave_accent", "toggle_flat", "Flat/Tree"),
    Binding("slash", "start_search", "Search"),
    Binding("minus", "collapse_all", "Collapse All"),
    Binding("equals_sign", "expand_all", "Expand All"),
    Binding("question_mark", "toggle_help", "Help"),
    Binding("backspace", "clear_field", "Clear Field", show=False),
    Binding("ctrl+r", "reset_guessit", "Reset to filename", show=False),
    Binding("tab", "tab_forward", "Tab"),
]
```

Removed: `h,left` / `l,right` cursor bindings (now handled in `on_key`),
`ctrl+a` (accept all), `c` (commit), `f` (extract filename).

Added: `e` (edit), `ctrl+r` (reset to filename), `tab` (tab forward).

**Step 2: Add new action handlers and modify existing ones**

Replace `action_toggle_or_enter` with `action_primary_action`:

```python
def action_primary_action(self) -> None:
    """Enter key: context-dependent primary action."""
    if self._mode == AppMode.COMMIT:
        cv = self.query_one(CommitView)
        self._do_commit(cv.operation)
        return
    if self._mode == AppMode.DETAIL:
        dv = self.query_one(DetailView)
        if dv.editing:
            dv.commit_edit()
        else:
            self._accept_detail_and_return()
        return
    if self._mode != AppMode.TREE:
        return
    tv = self.query_one(TreeView)
    if tv.in_range_mode:
        nodes = tv.selected_nodes()
        file_nodes = [n for n in nodes if isinstance(n, FileNode)]
        if file_nodes:
            self._show_detail_multi(file_nodes)
        tv.clear_range_select()
        return
    node = tv.cursor_node()
    if isinstance(node, FolderNode):
        # Select all files recursively and open detail view
        files = self._collect_folder_files(node)
        if files:
            self._show_detail_multi(files)
    elif isinstance(node, FileNode):
        self._toggle_staged_with_gate(node)
```

Add helper `_collect_folder_files`:

```python
def _collect_folder_files(self, folder: FolderNode) -> list[FileNode]:
    """Collect all file nodes under a folder recursively."""
    from tapes.tree_model import collect_files
    return collect_files(folder)
```

Add `_toggle_staged_with_gate`:

```python
def _toggle_staged_with_gate(self, node: FileNode) -> None:
    """Toggle staging with the can_fill_template gate."""
    from tapes.ui.tree_render import can_fill_template

    mt, tt = self.movie_template, self.tv_template

    def _can_stage(n: FileNode) -> bool:
        return can_fill_template(n, n.result, mt, tt)

    old = node.staged
    self.model.toggle_staged(node, can_stage=_can_stage)
    if not old and not node.staged:
        self.notify("Incomplete metadata -- cannot stage")
    self.query_one(TreeView).refresh()
    self._update_footer()
```

Add `_accept_detail_and_return`:

```python
def _accept_detail_and_return(self) -> None:
    """Accept detail view changes, auto-stage if possible, return to tree."""
    from tapes.ui.tree_render import can_fill_template

    mt, tt = self.movie_template, self.tv_template
    if self._detail_snapshot:
        for snap in self._detail_snapshot:
            node = snap.node
            if can_fill_template(node, node.result, mt, tt):
                node.staged = True
    self._detail_snapshot = None
    self._show_tree()
```

Replace `action_toggle_staged`:

```python
def action_toggle_staged(self) -> None:
    if self._mode != AppMode.TREE:
        return
    tv = self.query_one(TreeView)
    node = tv.cursor_node()
    if isinstance(node, FileNode):
        self._toggle_staged_with_gate(node)
    elif isinstance(node, FolderNode):
        from tapes.ui.tree_render import can_fill_template
        mt, tt = self.movie_template, self.tv_template
        self.model.toggle_staged_recursive(
            node,
            can_stage=lambda n: can_fill_template(n, n.result, mt, tt),
        )
        tv.refresh()
        self._update_footer()
```

Add `action_tab_forward`:

```python
def action_tab_forward(self) -> None:
    """Tab key: open commit preview from tree, cycle sources in detail."""
    if self._mode == AppMode.DETAIL:
        self.query_one(DetailView).cycle_source(1)
        return
    if self._mode != AppMode.TREE:
        return
    tv = self.query_one(TreeView)
    if tv.staged_count == 0:
        self.notify("No staged files to commit")
        return
    self._show_commit()
```

Add `action_start_edit`:

```python
def action_start_edit(self) -> None:
    """e key: start inline edit in detail view."""
    if self._mode != AppMode.DETAIL:
        return
    self.query_one(DetailView).start_edit()
```

Replace `action_cursor_left` / `action_cursor_right` to handle
tree collapse/expand:

```python
def action_cursor_left(self) -> None:
    """Left/h: collapse folder in tree, no-op in other modes."""
    pass  # handled in on_key now

def action_cursor_right(self) -> None:
    """Right/l: expand folder in tree, no-op in other modes."""
    pass  # handled in on_key now
```

Update `on_key` (in the existing method around line 748) to handle
h/l/left/right for tree collapse/expand and shift+tab:

Add this block at the start of `on_key`, before the ctrl+c check:

```python
# h/left = collapse, l/right = expand in tree mode
if self._mode == AppMode.TREE and event.key in ("h", "left"):
    tv = self.query_one(TreeView)
    node = tv.cursor_node()
    if isinstance(node, FolderNode) and not node.collapsed:
        tv.toggle_folder_at_cursor()
    else:
        tv.move_to_parent()
    event.prevent_default()
    event.stop()
    return
if self._mode == AppMode.TREE and event.key in ("l", "right"):
    tv = self.query_one(TreeView)
    node = tv.cursor_node()
    if isinstance(node, FolderNode) and node.collapsed:
        tv.toggle_folder_at_cursor()
    event.prevent_default()
    event.stop()
    return
```

Also update shift+tab handling (existing block around line 776):

```python
if event.key == "shift+tab":
    if self._mode == AppMode.DETAIL:
        self.query_one(DetailView).toggle_column_focus()
    elif self._mode == AppMode.COMMIT:
        self.query_one(CommitView).cycle_operation()
    else:
        self.query_one(BottomBar).cycle_operation()
    event.prevent_default()
    event.stop()
    return
```

Remove `action_commit` entirely (replaced by `action_tab_forward`).
Remove `action_apply_all_clear` (replaced by column focus + enter).
Remove `action_reset_guessit` -- rename to new binding handled by
`action_reset_guessit` but bound to `ctrl+r` instead of `f`.

**Step 3: Update `action_cancel` for detail view**

In the existing `action_cancel` method, the DETAIL branch (around line 478)
currently checks `dv.editing` then calls `_discard_detail()`. Keep this
behavior (esc in detail = discard).

**Step 4: Check TreeView has `move_to_parent` method**

If `move_to_parent` doesn't exist in `tapes/ui/tree_view.py`, add it:

```python
def move_to_parent(self) -> None:
    """Move cursor to the parent folder of the current node."""
    node = self.cursor_node()
    if node is None:
        return
    items = self._visible_items()
    # Find the parent folder by walking backwards
    current_depth = None
    cursor_idx = self._cursor
    for i, (item, depth) in enumerate(items):
        if i == cursor_idx:
            current_depth = depth
            break
    if current_depth is None or current_depth == 0:
        return
    for i in range(cursor_idx - 1, -1, -1):
        item, depth = items[i]
        if isinstance(item, FolderNode) and depth < current_depth:
            self._cursor = i
            self.refresh()
            return
```

**Step 5: Update footer hints**

In `tapes/ui/tree_app.py`, update `_update_footer` (line 882):

```python
bar.hint_text = "enter/space to stage \u00b7 tab to commit \u00b7 ? for help"
```

**Step 6: Write tests for the new tree keybindings**

Update existing tests in `tests/test_ui/test_tree_app.py`:

The existing tests that press `c` for commit need to press `tab` instead.
The existing tests that press `enter` on files to open detail need to be
updated -- `enter` on files now toggles staging.

Write new tests:

```python
class TestTreeKeyRedesign:
    @pytest.mark.asyncio()
    async def test_enter_stages_file(self) -> None:
        """enter on a file toggles staging."""
        app, model = _make_app_with_files(["movie.mkv"])
        node = model.all_files()[0]
        node.result = {MEDIA_TYPE: "movie", TITLE: "Test", YEAR: 2020}
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert node.staged is True

    @pytest.mark.asyncio()
    async def test_enter_blocked_incomplete(self) -> None:
        """enter on a file with incomplete metadata does not stage."""
        app, model = _make_app_with_files(["movie.mkv"])
        node = model.all_files()[0]
        node.result = {MEDIA_TYPE: "movie", TITLE: "Test"}  # no year
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert node.staged is False

    @pytest.mark.asyncio()
    async def test_tab_opens_commit_view(self) -> None:
        """tab from tree opens commit preview when files are staged."""
        app, model = _make_app_with_files(["movie.mkv"])
        node = model.all_files()[0]
        node.result = {MEDIA_TYPE: "movie", TITLE: "Test", YEAR: 2020}
        node.staged = True
        async with app.run_test() as pilot:
            await pilot.press("tab")
            assert app.mode == AppMode.COMMIT

    @pytest.mark.asyncio()
    async def test_h_collapses_folder(self) -> None:
        """h collapses an expanded folder."""
        # build a model with a folder containing a file
        ...

    @pytest.mark.asyncio()
    async def test_l_expands_folder(self) -> None:
        """l expands a collapsed folder."""
        ...
```

**Step 7: Run all tests, fix any regressions**

Run: `uv run pytest tests/test_ui/test_tree_app.py -v`

Many existing tests will need updating since:
- `c` no longer opens commit (use `tab`)
- `enter` on files no longer opens detail (stages instead)
- `enter` on folders no longer toggles collapse (opens detail for all files)

Fix each failing test to use the new keybindings.

**Step 8: Commit**

```bash
git add tapes/ui/tree_app.py tapes/ui/tree_view.py tests/test_ui/test_tree_app.py
git commit -m "feat: rewire tree view keybindings (enter=stage, tab=commit, h/l=collapse/expand)"
```

---

### Task 3: Detail view column focus model

Add a "focused column" concept: result or match. Tab cycles matches
(focuses match column), shift+tab toggles between result and match.
Enter accepts focused column and returns to tree. Light purple background
on focused column values.

**Files:**
- Modify: `tapes/ui/detail_view.py`
- Modify: `tapes/ui/detail_render.py`
- Modify: `tapes/ui/tree_render.py` (add COLUMN_FOCUS_BG color constant)
- Test: `tests/test_ui/test_detail_view.py`

**Step 1: Add the color constant**

In `tapes/ui/tree_render.py`, after the existing color constants (around
line 26), add:

```python
COLUMN_FOCUS_BG = "on #3B3154"  # Light purple for focused column in detail view
```

**Step 2: Add column focus state to DetailView**

In `tapes/ui/detail_view.py`, add a reactive for the focused column:

```python
# "result" or "match" -- which column enter will accept
focus_column: reactive[str] = reactive("match")
```

Add a `toggle_column_focus` method:

```python
def toggle_column_focus(self) -> None:
    """Toggle focus between result and match columns."""
    if self.focus_column == "result":
        self.focus_column = "match"
    else:
        self.focus_column = "result"
    self.refresh()
```

Update `cycle_source` to set focus to match:

```python
def cycle_source(self, delta: int) -> None:
    """Cycle through source tabs."""
    if self.editing:
        return
    sources = self.node.sources
    if not sources:
        return
    self.source_index = (self.source_index + delta) % len(sources)
    self.focus_column = "match"
    self.refresh()
```

Update `set_node` and `set_nodes` to reset `focus_column` to `"match"`:

```python
self.focus_column = "match"
```

**Step 3: Write failing test for column focus rendering**

In `tests/test_ui/test_detail_view.py`:

```python
class TestColumnFocus:
    def test_default_focus_is_match(self) -> None:
        view = _make_detail_view()
        assert view.focus_column == "match"

    def test_toggle_switches_to_result(self) -> None:
        view = _make_detail_view()
        view.toggle_column_focus()
        assert view.focus_column == "result"

    def test_toggle_back_to_match(self) -> None:
        view = _make_detail_view()
        view.toggle_column_focus()
        view.toggle_column_focus()
        assert view.focus_column == "match"

    def test_cycle_source_sets_focus_to_match(self) -> None:
        view = _make_detail_view_with_sources()
        view.focus_column = "result"
        view.cycle_source(1)
        assert view.focus_column == "match"
```

**Step 4: Run tests, verify failure, implement, verify pass**

Run: `uv run pytest tests/test_ui/test_detail_view.py::TestColumnFocus -v`

**Step 5: Update `_render_field_row` for column focus background**

In `tapes/ui/detail_view.py`, modify `_render_field_row` (around line 282).

Import the new constant:
```python
from tapes.ui.tree_render import COLUMN_FOCUS_BG
```

In the value column section (around lines 306-313), add the focused
background. After building the value text:

```python
# Value (editable)
result_raw = shared.get(field_name)
if self.editing and is_cursor:
    edit_display = self.edit_value + "\u2588"
    line.append(self._col(edit_display, val_w), style="underline")
else:
    result_val = display_val(result_raw)
    val_style = "bold" if is_cursor else ""
    if self.focus_column == "result":
        val_style += f" {COLUMN_FOCUS_BG}"
    line.append(self._col(result_val, val_w), style=val_style)
```

In the source value section (around lines 316-324):

```python
if sources and src_w > 0 and self.source_index < len(sources):
    src = sources[self.source_index]
    src_raw = src.fields.get(field_name)
    src_val = display_val(src_raw)

    line.append(COL_GAP)

    base_style = "dim" if is_multi_value(result_raw) else diff_style(result_raw, src_raw)
    if self.focus_column == "match":
        base_style += f" {COLUMN_FOCUS_BG}"
    line.append(self._col(src_val, src_w), style=base_style)
```

**Step 6: Update `accept_focused_column` method**

Add a new method that replaces `apply_source_all_clear`:

```python
def accept_focused_column(self) -> None:
    """Accept the focused column's values.

    If match is focused, copies non-None fields from the current
    source to the result (preserving fields the source doesn't have).
    If result is focused, no changes needed -- result is kept as-is.
    """
    if self.focus_column == "match":
        self.apply_source_all_clear()
```

**Step 7: Update detail view `on_key` for new bindings**

Replace the `on_key` method in `detail_view.py`:

```python
def on_key(self, event: events.Key) -> None:
    """Handle key events for inline editing and tab cycling."""
    if event.key == "tab" and not self.editing:
        self.cycle_source(1)
        event.prevent_default()
        event.stop()
        return

    if not self.editing:
        return

    if event.key == "enter":
        self.commit_edit()
        event.prevent_default()
        event.stop()
    elif event.key == "escape":
        self.cancel_edit()
        event.prevent_default()
        event.stop()
    elif event.key == "backspace":
        self.edit_value = self.edit_value[:-1]
        self.refresh()
        event.prevent_default()
        event.stop()
    elif event.character and event.is_printable:
        self.edit_value += event.character
        self.refresh()
        event.prevent_default()
        event.stop()
```

(This is nearly identical to the current version -- the main change is
that `tab` in non-editing mode cycles sources and sets focus to match.
The `shift+tab` toggle is handled in `tree_app.py`'s `on_key`.)

**Step 8: Update footer hints in detail view**

In `detail_view.py`, update `_render_footer_hints` (line 267):

```python
def _render_footer_hints(self) -> Text:
    """Render contextual footer hints based on editing state."""
    if self.quit_hint:
        return Text(f"    {self.quit_hint}", style=f"italic {MUTED}")
    if self.editing:
        return Text(
            "    enter to confirm \u00b7 esc to cancel",
            style=f"italic {MUTED}",
        )
    hints = (
        "    enter to accept \u00b7 esc to discard"
        " \u00b7 e to edit \u00b7 tab/shift+tab to cycle matches"
        " \u00b7 r to refresh \u00b7 ctrl+r to reset from filename"
    )
    return Text(hints, style=f"italic {MUTED}")
```

**Step 9: Write rendering tests**

Add tests verifying the purple background appears on the correct column.
Use `_render_field_row` or full `_build_content` and check for the
`COLUMN_FOCUS_BG` style in the returned Text spans.

**Step 10: Run all detail view tests**

Run: `uv run pytest tests/test_ui/test_detail_view.py -v`
Fix any regressions from the changed key handling.

**Step 11: Commit**

```bash
git add tapes/ui/detail_view.py tapes/ui/detail_render.py tapes/ui/tree_render.py tapes/ui/tree_app.py tests/test_ui/test_detail_view.py
git commit -m "feat: add column focus model to detail view with purple highlight"
```

---

### Task 4: Wire up enter-to-accept in detail view via tree_app

Connect the detail view column focus to the tree app: enter accepts
focused column, auto-stages if template complete, returns to tree.

**Files:**
- Modify: `tapes/ui/tree_app.py`
- Test: `tests/test_ui/test_tree_app.py`

**Step 1: Write failing Pilot test**

```python
@pytest.mark.asyncio()
async def test_enter_in_detail_accepts_match_and_stages(self) -> None:
    """enter in detail view accepts match, stages file, returns to tree."""
    app, model = _make_app_with_files(["movie.mkv"])
    node = model.all_files()[0]
    node.result = {MEDIA_TYPE: "movie", TITLE: "Old"}
    node.sources = [Source(origin="tmdb", fields={TITLE: "Inception", YEAR: 2010}, confidence=0.9)]
    async with app.run_test() as pilot:
        # Navigate to file and open detail (enter on file = stage, but
        # incomplete metadata blocks it, so we need to open detail differently)
        # Actually, enter on a file with complete metadata stages it.
        # For detail view, we need to go via a folder or range select.
        # Or set up a file where enter opens detail (via range select).
        ...
```

Note: Since `enter` on files now stages (not opens detail), opening detail
view requires either: (a) enter on a folder, or (b) `v` for range select
then enter. The tests need to account for this.

**Step 2: Verify `_accept_detail_and_return` calls `accept_focused_column`**

The `_accept_detail_and_return` method (added in Task 2) should first
apply the focused column, then auto-stage:

```python
def _accept_detail_and_return(self) -> None:
    """Accept detail view changes, auto-stage if possible, return to tree."""
    from tapes.ui.tree_render import can_fill_template

    dv = self.query_one(DetailView)
    dv.accept_focused_column()

    mt, tt = self.movie_template, self.tv_template
    if self._detail_snapshot:
        for snap in self._detail_snapshot:
            node = snap.node
            if can_fill_template(node, node.result, mt, tt):
                node.staged = True
    self._detail_snapshot = None
    self._show_tree()
```

**Step 3: Run all tree app tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py -v`

**Step 4: Commit**

```bash
git add tapes/ui/tree_app.py tests/test_ui/test_tree_app.py
git commit -m "feat: enter in detail view accepts focused column and auto-stages"
```

---

### Task 5: Update help overlay

Update keybinding reference text to match the new design.

**Files:**
- Modify: `tapes/ui/help_overlay.py`
- Test: `tests/test_ui/test_help_overlay.py`

**Step 1: Update help content**

In `tapes/ui/help_overlay.py`, replace the keybinding sections in
`_build_help_content` (around lines 49-83):

```python
# File browser keys
lines.append(heading("File browser"))
lines.append(key_row("j / k", "move cursor"))
lines.append(key_row("enter", "stage file or open folder detail"))
lines.append(key_row("space", "stage / unstage for commit"))
lines.append(key_row("h / l", "collapse / expand folder"))
lines.append(key_row("x", "ignore file (skip entirely)"))
lines.append(key_row("v", "start visual range select"))
lines.append(key_row("/", "search and filter"))
lines.append(key_row("r", "re-query TMDB with current metadata"))
lines.append(key_row("tab", "open commit preview"))
lines.append(key_row("shift+tab", "cycle operation (copy/move/link/hardlink)"))
lines.append(key_row("ctrl+c ctrl+c", "quit"))
lines.append(Text())

# Detail view keys
lines.append(heading("Detail view"))
lines.append(key_row("enter", "accept focused column and return"))
lines.append(key_row("esc", "discard changes and return"))
lines.append(key_row("e", "edit field value inline"))
lines.append(key_row("backspace", "clear field"))
lines.append(key_row("tab", "cycle TMDB matches"))
lines.append(key_row("shift+tab", "toggle focus: result / match"))
lines.append(key_row("r", "refresh TMDB matches"))
lines.append(key_row("ctrl+r", "reset field from filename"))
lines.append(Text())

# Tips
lines.append(heading("Tips"))
lines.append(body("High-confidence TMDB matches are auto-accepted and staged."))
lines.append(body("Files need complete metadata before they can be staged."))
lines.append(body("\u2610 means ready to stage, \u2713 means staged."))
lines.append(body("Use v to select a range, then enter to bulk-edit metadata."))
lines.append(Text())
```

Update `HELP_HEIGHT` at line 17 to match the new line count (count all
lines including blanks and separators).

**Step 2: Update help overlay tests**

In `tests/test_ui/test_help_overlay.py`, update any assertions that check
for specific key descriptions (e.g., "c" for commit, "ctrl+a" for accept).

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_help_overlay.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add tapes/ui/help_overlay.py tests/test_ui/test_help_overlay.py
git commit -m "docs: update help overlay for new keybindings"
```

---

### Task 6: Fix all remaining test regressions

Run the full test suite and fix every failing test. This task is about
adapting existing tests to the new keybinding scheme, not writing new
functionality.

**Files:**
- Modify: `tests/test_ui/test_tree_app.py` (most changes here)
- Modify: `tests/test_ui/test_detail_view.py`
- Possibly: `tests/test_ui/test_commit_view.py`

**Step 1: Run full test suite**

Run: `uv run pytest -v 2>&1 | head -100`

**Step 2: Identify and fix each failure**

Common patterns to fix:

- Tests pressing `c` to open commit -> change to `tab`
- Tests pressing `c` to confirm detail -> change to `enter`
- Tests pressing `enter` on a file expecting detail view -> use folder
  enter or range select + enter instead
- Tests pressing `ctrl+a` to accept match -> set `focus_column = "match"`
  and press `enter`
- Tests pressing `f` to reset guessit -> press `ctrl+r`
- Tests pressing `left`/`right` in detail to cycle sources -> use `tab`
- Tests checking `action_commit` -> check `action_tab_forward`

**Step 3: Run full suite until all pass**

Run: `uv run pytest -v`
Expected: ALL PASS (667+ tests)

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: update all tests for new keybinding scheme"
```

---

### Summary of key changes

| Old | New | Context |
|-----|-----|---------|
| `enter` on file | opens detail | now stages/unstages |
| `enter` on folder | toggles collapse | now opens detail for all files |
| `h` / `left` | (unused in tree) | collapse folder |
| `l` / `right` | (unused in tree) | expand folder |
| `c` (tree) | open commit | removed (use `tab`) |
| `c` (detail) | confirm changes | removed (use `enter`) |
| `c` (commit) | process files | removed (use `enter`) |
| `tab` (tree) | (unused) | open commit preview |
| `tab` (detail) | cycle sources | cycle sources (unchanged) |
| `shift+tab` (detail) | (unused) | toggle column focus |
| `ctrl+a` | accept all from match | removed (use column focus + enter) |
| `f` | extract from filename | removed (use `ctrl+r`) |
| `e` | (unused) | start edit in detail |
| `space` | stage/unstage | stage/unstage with gate |
| staging | always allowed | blocked if template incomplete |
