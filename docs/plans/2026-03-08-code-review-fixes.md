# Code Review Fixes Implementation Plan

Status: **completed** (merged to main 2026-03-08)

**Goal:** Fix detail view keybinding model (confirm/discard instead of auto-write+undo), remove undo globally, add missing keybindings (d, g, tab, shift-tab), fix dimming, normalize shortcut text, rewrite help overlay.

**Architecture:** Detail mode becomes a staging area: edits are pending until `c` confirms them; `esc` discards. UndoManager is removed entirely. Shift+tab and tab are intercepted in `on_key` to bypass Textual's focus cycling. Private DetailView API is made public. All user-facing shortcut text uses lowercase with `shift-`/`ctrl`/`esc` formatting.

**Tech Stack:** Textual 8, Rich Text, Python 3.11+

---

### Task 1: Add `extract_guessit_fields` helper to `pipeline.py`

Needed later by the `g` (reset to guessit) keybinding.

**Files:**
- Modify: `tapes/ui/pipeline.py`
- Test: `tests/test_ui/test_pipeline.py`

**Step 1: Write failing test**

Add to `tests/test_ui/test_pipeline.py`:

```python
class TestExtractGuessitFields:
    def test_extracts_title_and_year(self) -> None:
        from tapes.ui.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("Inception.2010.mkv")
        assert fields["title"] == "Inception"
        assert fields["year"] == 2010

    def test_extracts_tv_fields(self) -> None:
        from tapes.ui.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("Breaking.Bad.S01E01.mkv")
        assert fields["title"] == "Breaking Bad"
        assert fields["season"] == 1
        assert fields["episode"] == 1

    def test_missing_fields_omitted(self) -> None:
        from tapes.ui.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("something.mkv")
        # No year key if guessit can't find one
        assert "year" not in fields or fields.get("year") is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestExtractGuessitFields -v`
Expected: FAIL with ImportError

**Step 3: Implement**

Add to `tapes/ui/pipeline.py`, after `_populate_node_guessit`:

```python
def extract_guessit_fields(filename: str) -> dict[str, Any]:
    """Extract metadata fields from a filename via guessit.

    Returns the same field dict that run_guessit_pass would populate.
    """
    from tapes.metadata import extract_metadata

    meta = extract_metadata(filename)
    fields: dict[str, Any] = {}
    if meta.title:
        fields[TITLE] = meta.title
    if meta.year is not None:
        fields[YEAR] = meta.year
    if meta.season is not None:
        fields[SEASON] = meta.season
    if meta.episode is not None:
        fields[EPISODE] = meta.episode
    if meta.media_type:
        fields[MEDIA_TYPE] = meta.media_type
    for k, v in meta.raw.items():
        if v is not None:
            fields[k] = v
    return fields
```

Also add `Any` to the existing `typing` import if not present.

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestExtractGuessitFields -v`
Expected: PASS

**Step 5: Commit**

```
feat: add extract_guessit_fields helper for per-field guessit reset
```

---

### Task 2: Remove UndoManager and all undo wiring

**Files:**
- Modify: `tapes/ui/tree_model.py` — delete `UndoManager` class
- Modify: `tapes/ui/tree_app.py` — remove undo binding, action, snapshot calls
- Modify: `tapes/ui/detail_view.py` — remove `on_before_mutate` callback
- Modify: `tests/test_ui/test_tree_app.py` — delete undo tests
- Modify: `tests/test_ui/test_tree_model.py` — delete UndoManager import if unused

**Step 1: Remove `UndoManager` class from `tapes/ui/tree_model.py`**

Delete the entire `UndoManager` class (lines 213-244). Also remove `import copy` if no longer used.

**Step 2: Remove undo wiring from `tapes/ui/tree_app.py`**

1. Remove import: `UndoManager` from the `tree_model` import line.
2. Remove binding: `Binding("u", "undo", "Undo")` from `BINDINGS`.
3. Remove `self._undo = UndoManager()` from `__init__`.
4. Remove `_snapshot_before_mutate` method entirely.
5. Remove `action_undo` method entirely.
6. Remove `detail.on_before_mutate = self._snapshot_before_mutate` from `_show_detail` and `_show_detail_multi`.
7. Remove all `self._undo.snapshot(...)` calls in `action_refresh_query` and `action_accept_best`.

**Step 3: Remove `on_before_mutate` from `tapes/ui/detail_view.py`**

1. Remove `self.on_before_mutate` from `__init__` (line 66).
2. Remove `_notify_before_mutate` method entirely (lines 349-352).
3. Remove calls to `self._notify_before_mutate()` in `apply_source_field` (line 368), `apply_source_all_clear` (line 384), and `_commit_edit` (line 412).

**Step 4: Remove undo tests from `tests/test_ui/test_tree_app.py`**

Delete the `TestUndoManager` class and the `TestUndoIntegration` class entirely.

**Step 5: Remove stale imports**

In `tests/test_ui/test_tree_model.py`, remove `UndoManager` from imports if present.
In `tapes/ui/tree_app.py`, verify `UndoManager` is no longer imported.

**Step 6: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS (minus the deleted undo tests)

**Step 7: Commit**

```
refactor: remove UndoManager and all undo wiring
```

---

### Task 3: Make DetailView API public

Rename private attributes/methods that TreeApp accesses directly.

**Files:**
- Modify: `tapes/ui/detail_view.py`
- Modify: `tapes/ui/tree_app.py`
- Modify: `tests/test_ui/test_detail_view.py`
- Modify: `tests/test_ui/test_tree_app.py`

**Step 1: Rename in `tapes/ui/detail_view.py`**

1. `_fields` → `fields` (attribute set in `__init__`, `on_mount`, `set_node`, `set_nodes`; used in `_compute_col_widths`, `_build_content`, `move_cursor`, `apply_source_field`, `apply_source_all_clear`, `_start_edit`, `_commit_edit`).
2. `_file_nodes` → `file_nodes` (attribute set in `__init__`, `set_node`, `set_nodes`; used in many methods).
3. `_start_edit` → `start_edit` (called from TreeApp).
4. `_cancel_edit` → `cancel_edit` (called from TreeApp).
5. `_commit_edit` → `commit_edit` (called internally, but make consistent).
6. `_edit_value` → `edit_value` (accessed in rendering and editing methods).

**Step 2: Update callers in `tapes/ui/tree_app.py`**

Replace all occurrences:
- `dv._start_edit()` → `dv.start_edit()`
- `dv._cancel_edit()` → `dv.cancel_edit()`
- `dv._fields` → `dv.fields`
- `dv._file_nodes` → `dv.file_nodes`

**Step 3: Update tests**

In `tests/test_ui/test_detail_view.py` and `tests/test_ui/test_tree_app.py`, replace all `._fields`, `._file_nodes`, `._start_edit`, `._cancel_edit`, `._edit_value` references with the public names.

**Step 4: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS

**Step 5: Commit**

```
refactor: make DetailView fields, file_nodes, and edit methods public
```

---

### Task 4: Detail view confirm/discard model

The core change. Edits in detail mode are pending until `c` confirms. `esc` discards.

**Files:**
- Modify: `tapes/ui/tree_app.py`
- Modify: `tapes/ui/detail_view.py`
- Modify: `tests/test_ui/test_tree_app.py`

**Step 1: Write failing tests**

Add to `tests/test_ui/test_tree_app.py`:

```python
class TestDetailConfirmDiscard:
    """Tests for the confirm/discard model in detail view."""

    @pytest.mark.asyncio()
    async def test_esc_discards_changes(self) -> None:
        """Pressing esc in detail mode restores original values."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Original"},
            sources=[Source(name="TMDB #1", fields={"title": "Changed"}, confidence=0.9)],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Enter detail mode
            await pilot.press("enter")
            assert app._in_detail

            # Apply all from source (modifies result)
            await pilot.press("shift+enter")
            assert node.result["title"] == "Changed"

            # Esc should discard
            await pilot.press("escape")
            assert not app._in_detail
            assert node.result["title"] == "Original"

    @pytest.mark.asyncio()
    async def test_c_confirms_changes(self) -> None:
        """Pressing c in detail mode keeps changes."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Original"},
            sources=[Source(name="TMDB #1", fields={"title": "Changed"}, confidence=0.9)],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.press("shift+enter")
            assert node.result["title"] == "Changed"

            # c should confirm
            await pilot.press("c")
            assert not app._in_detail
            assert node.result["title"] == "Changed"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_tree_app.py::TestDetailConfirmDiscard -v`
Expected: FAIL

**Step 3: Add snapshot storage to `tapes/ui/tree_app.py`**

Add import at top:
```python
import copy
```

Add to `__init__`:
```python
self._detail_snapshot: list[tuple[FileNode, dict, list, bool]] | None = None
```

**Step 4: Update `_show_detail` and `_show_detail_multi` to snapshot**

In `_show_detail`, after `self._in_detail = True`, before `detail.set_node(node)`:
```python
self._detail_snapshot = [
    (node, copy.deepcopy(node.result), copy.deepcopy(node.sources), node.staged)
]
```

In `_show_detail_multi`, same pattern but for all nodes:
```python
self._detail_snapshot = [
    (n, copy.deepcopy(n.result), copy.deepcopy(n.sources), n.staged)
    for n in nodes
]
```

**Step 5: Add `_confirm_detail` and `_discard_detail` methods**

```python
def _confirm_detail(self) -> None:
    """Confirm detail view changes and return to tree."""
    self._detail_snapshot = None
    self._show_tree()

def _discard_detail(self) -> None:
    """Discard detail view changes and return to tree."""
    if self._detail_snapshot:
        for node, result, sources, staged in self._detail_snapshot:
            node.result = result
            node.sources = sources
            node.staged = staged
        self._detail_snapshot = None
    self._show_tree()
```

**Step 6: Update `action_cancel` to call `_discard_detail`**

Change the `self._show_tree()` call in the `_in_detail` branch to `self._discard_detail()`.

**Step 7: Update `action_commit` to confirm in detail mode**

Change:
```python
def action_commit(self) -> None:
    if self._in_detail:
        self._confirm_detail()
        return
    # ... rest unchanged
```

**Step 8: Remove `a` from detail mode**

In `action_accept_best`, change the detail branch to do nothing:
```python
def action_accept_best(self) -> None:
    if self._in_detail:
        return
    # ... rest unchanged
```

**Step 9: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py::TestDetailConfirmDiscard -v`
Expected: PASS

Run: `uv run pytest -x`
Expected: PASS

**Step 10: Commit**

```
feat: detail view confirm/discard model (c to confirm, esc to discard)
```

---

### Task 5: Add new detail keybindings (d, g)

**Files:**
- Modify: `tapes/ui/detail_view.py` — add `clear_field` and `reset_field_to_guessit`
- Modify: `tapes/ui/tree_app.py` — add bindings and actions
- Modify: `tests/test_ui/test_detail_view.py` — add tests

**Step 1: Write failing tests**

Add to `tests/test_ui/test_detail_view.py`:

```python
class TestClearField:
    def test_clear_field_removes_value(self) -> None:
        node = FileNode(
            path=Path("/media/Inception.2010.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        dv = DetailView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        dv.fields = get_display_fields(dv._active_template())
        dv.cursor_row = 0  # title field
        dv.clear_field()
        assert "title" not in node.result


class TestResetFieldToGuessit:
    def test_reset_restores_guessit_value(self) -> None:
        node = FileNode(
            path=Path("/media/Inception.2010.mkv"),
            result={"title": "Wrong Title", "year": 2010, "media_type": "movie"},
        )
        dv = DetailView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        dv.fields = get_display_fields(dv._active_template())
        dv.cursor_row = 0  # title field (tmdb_id is first, then title)
        # Find the title field index
        dv.cursor_row = dv.fields.index("title")
        dv.reset_field_to_guessit()
        assert node.result["title"] == "Inception"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_detail_view.py::TestClearField -v`
Expected: FAIL with AttributeError

**Step 3: Implement `clear_field` and `reset_field_to_guessit` in `tapes/ui/detail_view.py`**

```python
def clear_field(self) -> None:
    """Clear the current field (remove from result)."""
    if self.editing:
        return
    field_name = self.fields[self.cursor_row]
    for n in self.file_nodes:
        n.result.pop(field_name, None)
    self.refresh()

def reset_field_to_guessit(self) -> None:
    """Reset the current field to its guessit-extracted value."""
    if self.editing:
        return
    from tapes.ui.pipeline import extract_guessit_fields

    field_name = self.fields[self.cursor_row]
    for n in self.file_nodes:
        guessit_fields = extract_guessit_fields(n.path.name)
        val = guessit_fields.get(field_name)
        if val is not None:
            n.result[field_name] = val
        else:
            n.result.pop(field_name, None)
    self.refresh()
```

**Step 4: Add bindings and actions in `tapes/ui/tree_app.py`**

Add to `BINDINGS`:
```python
Binding("d", "clear_field", "Clear Field", show=False),
Binding("g", "reset_guessit", "Reset Guessit", show=False),
```

Add actions:
```python
def action_clear_field(self) -> None:
    if not self._in_detail:
        return
    self.query_one(DetailView).clear_field()

def action_reset_guessit(self) -> None:
    if not self._in_detail:
        return
    self.query_one(DetailView).reset_field_to_guessit()
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_detail_view.py::TestClearField tests/test_ui/test_detail_view.py::TestResetFieldToGuessit -v`
Expected: PASS

**Step 6: Commit**

```
feat: add d (clear field) and g (reset to guessit) keybindings in detail view
```

---

### Task 6: Intercept tab and shift+tab in `on_key`

Textual captures `tab` and `shift+tab` for focus cycling. Intercept them.

**Files:**
- Modify: `tapes/ui/detail_view.py` — intercept `tab` for source cycling
- Modify: `tapes/ui/tree_app.py` — intercept `shift+tab` for op cycling, remove binding

**Step 1: Intercept `tab` in `tapes/ui/detail_view.py` `on_key`**

At the top of `on_key`, before the `if not self.editing` guard:

```python
def on_key(self, event: events.Key) -> None:
    """Handle key events for inline editing and tab cycling."""
    if event.key == "tab" and not self.editing:
        self.cycle_source(1)
        self.refresh()
        event.prevent_default()
        event.stop()
        return

    if not self.editing:
        return
    # ... existing editing key handling unchanged
```

**Step 2: Intercept `shift+tab` in `tapes/ui/tree_app.py` `on_key`**

Add at the top of `on_key`, before the search-mode guard:

```python
def on_key(self, event: Key) -> None:
    """Intercept key events for search mode and special bindings."""
    # Intercept shift+tab for op cycling (Textual captures it for focus)
    if event.key == "shift+tab" and not self._in_detail and not self._searching:
        self.action_cycle_op()
        event.prevent_default()
        event.stop()
        return

    if not self._searching:
        return
    # ... existing search handling unchanged
```

**Step 3: Remove the `shift+tab` Binding from `BINDINGS`**

Delete: `Binding("shift+tab", "cycle_op", "Cycle Op", show=False)`

The action method `action_cycle_op` stays (called from `on_key`).

**Step 4: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS

**Step 5: Commit**

```
fix: intercept tab and shift-tab in on_key to bypass Textual focus cycling
```

---

### Task 7: Fix dimming

**Files:**
- Modify: `tapes/ui/tree_app.py` — change CSS

**Step 1: Change dimming CSS**

Replace:
```css
TreeView.dimmed {
    color: #555555;
}
```

With:
```css
TreeView.dimmed {
    opacity: 0.4;
}
```

**Step 2: Run tests**

Run: `uv run pytest -x`
Expected: PASS

**Step 3: Commit**

```
fix: use opacity for detail-mode dimming instead of aggressive color override
```

---

### Task 8: Normalize shortcut text and rewrite help overlay

All user-facing shortcut text: lowercase, `shift-` not `⇧`, `esc` not `Escape`, `ctrl` not `Control`.

**Files:**
- Modify: `tapes/ui/tree_app.py` — footer hints
- Modify: `tapes/ui/detail_view.py` — footer hints, tab bar hint
- Modify: `tapes/ui/help_overlay.py` — full rewrite of keybinding reference
- Modify: `tapes/ui/commit_modal.py` — hint text
- Modify: `tests/test_ui/test_help_overlay.py` — update expected text

**Step 1: Update `tapes/ui/tree_app.py` `_update_footer`**

Change search hints (line 515):
```python
bar.hint_text = "enter to confirm · esc to cancel"
```

Change tree hints (line 517-520):
```python
bar.hint_text = (
    "space stage · enter details · a accept · "
    "shift-tab op · c commit · ? help"
)
```

**Step 2: Update `tapes/ui/detail_view.py` `_render_footer_hints`**

Editing mode:
```python
return Text(
    " enter to confirm · esc to cancel",
    style=f"italic {MUTED}",
)
```

Normal mode:
```python
return Text(
    " enter edit · shift-enter apply all · d clear · g guessit · tab sources · c confirm · esc discard",
    style=f"italic {MUTED}",
)
```

**Step 3: Update tab bar hint in `_render_tab_bar`**

Change `"←/→ to cycle"` (line 231) to `"h/l to cycle"`.

**Step 4: Update `tapes/ui/commit_modal.py`**

Change hint (line 33): `"←/→ to change"` → `"h/l to change"`

Change footer (line 38): already lowercase, keep as-is.

**Step 5: Rewrite `tapes/ui/help_overlay.py` `_build_help_text`**

Replace the entire function body with keybindings that match the actual implementation:

```python
def _build_help_text() -> Text:
    """Build the help content as a Rich Text object."""

    def key_row(key: str, action: str) -> Text:
        t = Text()
        t.append(f"  {key:<16}", "#7AB8FF")
        t.append(action)
        return t

    result = Text()

    result.append("  Files\n", "bold")

    file_keys = [
        ("j / k", "move cursor"),
        ("enter", "open detail / toggle folder"),
        ("space", "toggle staged"),
        ("a", "accept best TMDB match"),
        ("x", "toggle ignored"),
        ("v", "range select"),
        ("c", "commit staged files"),
        ("/", "search / filter"),
        ("`", "toggle flat/tree mode"),
        ("- / =", "collapse / expand all"),
        ("r", "refresh TMDB query"),
        ("shift-tab", "cycle operation mode"),
        ("q", "quit"),
    ]
    for key, action in file_keys:
        result.append_text(key_row(key, action))
        result.append("\n")

    result.append("\n")
    result.append("  Detail\n", "bold")

    detail_keys = [
        ("j / k", "move between fields"),
        ("tab / h / l", "cycle TMDB sources"),
        ("enter", "edit field inline"),
        ("shift-enter", "apply all fields from source"),
        ("d", "clear field"),
        ("g", "reset field to guessit value"),
        ("r", "refresh TMDB query"),
        ("c", "confirm changes"),
        ("esc", "discard changes"),
    ]
    for key, action in detail_keys:
        result.append_text(key_row(key, action))
        result.append("\n")

    result.append("\n")
    result.append("  Concepts\n", "bold")
    result.append(f"  {'staged':<16}file will be processed on commit\n")
    result.append(f"  {'unstaged':<16}needs review, check destination\n")
    result.append(f"  {'ignored':<16}skipped entirely\n")

    result.append("\n")
    result.append("  sources provide metadata from TMDB.\n", MUTED)
    result.append("  apply values to the result to build the destination path.\n", MUTED)

    result.append("\n")
    result.append("  press ? or esc to close\n", f"{MUTED} italic")

    return result
```

**Step 6: Update `tests/test_ui/test_help_overlay.py`**

Update any assertions that check for specific help text content to match the new text.

**Step 7: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS

**Step 8: Commit**

```
fix: normalize shortcut text to lowercase, rewrite help overlay to match keybindings
```

---

### Task 9: Clean up stale code

**Files:**
- Modify: `tapes/ui/tree_model.py` — remove `accept_best_source` import from tree_app if unused... actually it's still used in tree mode.
- Modify: `tapes/ui/tree_app.py` — remove `accept_best_source` import? No, it's still used.

Check: is `accept_best_source` still imported and used?
- `tree_app.py` imports `accept_best_source` and uses it in `action_accept_best` (tree mode).
- Keep it.

Check: is `compute_shared_fields` still used?
- `detail_view.py` imports it. Used in `_shared_result`. Keep it.

Check: is `UndoManager` still imported anywhere after Task 2?
- Should have been cleaned up in Task 2. Verify.

**Step 1: Verify no stale imports**

Run: `uv run pytest -x`
Expected: PASS

**Step 2: Commit (only if changes needed)**

```
refactor: remove stale imports
```

---

## Summary

| Task | What | Key files |
|------|------|-----------|
| 1 | `extract_guessit_fields` helper | pipeline.py |
| 2 | Remove UndoManager globally | tree_model.py, tree_app.py, detail_view.py |
| 3 | Make DetailView API public | detail_view.py, tree_app.py |
| 4 | Confirm/discard model + remove `a` from detail | tree_app.py |
| 5 | New keybindings: `d`, `g` | detail_view.py, tree_app.py |
| 6 | Intercept tab, shift-tab in on_key | detail_view.py, tree_app.py |
| 7 | Fix dimming (opacity) | tree_app.py |
| 8 | Normalize text + rewrite help overlay | tree_app.py, detail_view.py, help_overlay.py, commit_modal.py |
| 9 | Clean up stale code | verify imports |

**Final detail view keybindings:**

| Key | Action |
|-----|--------|
| j / k | move between fields |
| tab / h / l | cycle TMDB sources |
| enter | edit field inline |
| shift-enter | apply all fields from source |
| d | clear field |
| g | reset field to guessit value |
| r | refresh TMDB query |
| c | confirm changes |
| esc | discard changes |
