# TUI Visual Design Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update the TUI presentation to match the visual design spec — stacked panels with borders, semantic color system, one-source-at-a-time detail view, destination path coloring, context-aware footer, help/commit modals.

**Architecture:** The existing TUI (M1-M16) has all functionality but minimal styling. This plan adds visual polish without changing data models or pipeline logic. Changes touch rendering code (`tree_render.py`, `detail_render.py`), widget CSS/compose (`tree_app.py`, `tree_view.py`, `detail_view.py`), and add two new modal widgets.

**Tech Stack:** Python 3.11+, Textual (TUI framework), Rich (text styling). Tests with pytest + Textual Pilot.

**Design references:**
- `docs/plans/2026-03-07-tui-visual-design.md` — authoritative spec
- `docs/mockups/tui-visual-design.html` — visual mockups
- `docs/plans/2026-03-07-tui-walkthrough-draft.md` — user-facing walkthrough

---

## Task 1: Stacked Panel Layout

Both panels always visible. Tree on top (most space), detail on bottom. Detail is compact (2-3 rows) when tree is focused, expands when detail is focused. Currently the app toggles `display: none` on DetailView.

**Files:**
- Modify: `tapes/ui/tree_app.py` (CSS at lines 49-57, compose at lines 84-99, `_enter_detail`/`_leave_detail` around lines 140-172)
- Test: `tests/test_ui/test_tree_app.py`

**Step 1: Update CSS for stacked layout**

Replace the current CSS block (lines 49-57) with height-based stacking. Tree gets `3fr` when focused, `auto` (5 rows) when detail is focused. Detail gets `auto` (3 rows) when tree is focused, `1fr` when detail is focused. Use Textual CSS classes to toggle.

```python
CSS = """
Screen {
    layout: vertical;
}
TreeView {
    height: 3fr;
}
TreeView.compressed {
    height: 7;
}
DetailView {
    height: 5;
}
DetailView.expanded {
    height: 1fr;
}
Footer {
    dock: bottom;
    height: 1;
}
"""
```

**Step 2: Update compose to always show DetailView**

Remove `display: none` from DetailView. Both widgets always rendered. In `compose()`, yield TreeView, DetailView, Footer (remove Header and Static #status — status moves into tree panel border in a later task).

```python
def compose(self) -> ComposeResult:
    yield TreeView(id="tree")
    yield DetailView(id="detail")
    yield Footer()
```

**Step 3: Update detail toggle to use CSS classes instead of display**

In `_enter_detail()`: add class "compressed" to TreeView, add class "expanded" to DetailView.
In `_leave_detail()`: remove those classes.

```python
def _enter_detail(self) -> None:
    self._in_detail = True
    self.query_one(TreeView).add_class("compressed")
    self.query_one(DetailView).add_class("expanded")
    # ... existing logic to populate detail view

def _leave_detail(self) -> None:
    self._in_detail = False
    self.query_one(TreeView).remove_class("compressed")
    self.query_one(DetailView).remove_class("expanded")
```

**Step 4: Update DetailView to show compact preview when not expanded**

In `detail_view.py`, when `_file_nodes` is set but the view is not expanded (no "expanded" class), render a 2-line compact preview. When expanded, render the full grid. Check `self.has_class("expanded")` in `render()`.

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/ -v`

Existing tests may fail because of layout changes (display: none removal, Header/Static removal). Fix test assertions that check for hidden widgets or specific widget counts.

**Step 6: Commit**

```
feat: stacked panel layout with tree and detail always visible
```

---

## Task 2: Box-Drawing Panel Borders

Panels use box-drawing characters. Active panel has cyan border, inactive has dim border. Panel titles embedded in top border.

**Files:**
- Modify: `tapes/ui/tree_view.py` (render method, lines 147-181)
- Modify: `tapes/ui/detail_view.py` (render method, lines 104-132)
- Modify: `tapes/ui/tree_app.py` (pass active state to widgets)
- Test: `tests/test_ui/test_tree_view.py`, `tests/test_ui/test_detail_view.py`

**Step 1: Add `active` reactive property to both widgets**

```python
class TreeView(Static):
    active: reactive[bool] = reactive(True)
```

```python
class DetailView(Static):
    active: reactive[bool] = reactive(False)
```

TreeApp toggles these in `_enter_detail` / `_leave_detail`.

**Step 2: Implement border rendering in TreeView.render()**

Wrap the tree content in box-drawing borders. The top border includes the panel title ("Files"). The bottom border includes status info (staged/ignored/total counts — currently in the Static #status widget).

```python
def render(self) -> RenderableType:
    width = self.size.width
    border_style = "cyan" if self.active else "dim"
    title = " Files "

    # Top border: ┌─ Files ─────────┐
    top = f"┌─{title}" + "─" * (width - len(title) - 4) + "─┐"

    # Content rows (existing logic, prefixed with │ and suffixed with │)
    rows = []
    for i, (node, depth) in enumerate(self._items):
        line = render_row(node, depth, ...)  # existing
        padded = line.ljust(width - 4)  # pad to fill width minus borders
        row_text = Text(f"│ {padded} │")
        # ... apply existing styling (dim, reverse, etc.)
        rows.append(row_text)

    # Bottom border with status: ├── 2 staged / 1 ignored / 7 total ──┤
    status = self._compute_status_text()
    bot = f"├─── {status} " + "─" * (width - len(status) - 7) + "─┤"

    # Apply border_style color to border characters
    result = Text(top + "\n")
    result.stylize(border_style)
    for row in rows:
        result.append(row)
        result.append("\n")
    bot_text = Text(bot)
    bot_text.stylize(border_style)
    result.append(bot_text)
    return result
```

**Step 3: Implement border rendering in DetailView.render()**

Same approach. Top border: `├─ Detail ────┤` (uses `├` and `┤` because it shares border with tree panel above). Bottom border: `└────────────┘`.

**Step 4: Write tests for border output**

Test that `render()` output starts with `┌─ Files` and ends with border characters. Test that active/inactive toggles the style.

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/ -v`

**Step 6: Commit**

```
feat: box-drawing panel borders with active/inactive styling
```

---

## Task 3: Tree View Color System

Apply the semantic color system to tree rows. Staging markers get color. Ignored files get dim. Cursor gets selection background.

**Files:**
- Modify: `tapes/ui/tree_render.py` (new function `style_file_row` or modify `render_file_row`)
- Modify: `tapes/ui/tree_view.py` (apply styles in render loop)
- Test: `tests/test_ui/test_tree_render.py`

**Step 1: Add color constants**

In `tree_render.py`, add style constants:

```python
STYLE_STAGED = "green"
STYLE_UNSTAGED = "yellow"
STYLE_IGNORED = "dim"
STYLE_CURSOR = "reverse"
STYLE_RANGE_SELECT = "on dark_blue"
STYLE_FOLDER_ARROW = ""  # default fg
```

**Step 2: Update render_file_row to return Rich Text with styled marker**

Currently `render_file_row` returns a plain string. Change it to return `Rich.Text` with the marker styled:

```python
def render_file_row(node, depth, template, flat_mode=False) -> Text:
    indent = "" if flat_mode else "  " * depth
    if node.ignored:
        marker = "·"
        marker_style = STYLE_IGNORED
    elif node.staged:
        marker = "✓"
        marker_style = STYLE_STAGED
    else:
        marker = "○"
        marker_style = STYLE_UNSTAGED

    text = Text()
    text.append(f"{indent}")
    text.append(marker, marker_style)
    text.append(f" {node.path.name}")
    # ... destination part (Task 4)
    return text
```

**Step 3: Update TreeView.render() to use Rich Text objects**

Replace the current string-based approach with Rich Text composition. Apply cursor/selection styling as overlays on the Text objects.

**Step 4: Update tests**

Tests in `test_tree_render.py` currently check plain string output. Update to check Rich Text content or add new tests for styled output. Keep existing plain-string tests if `render_file_row` still supports them (or create a separate `render_file_row_plain` for tests).

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_render.py -v`

**Step 6: Commit**

```
feat: colored staging markers in tree view
```

---

## Task 4: Destination Path Coloring

Directory path and extension dim, filename stem normal, unresolved `?` yellow.

**Files:**
- Modify: `tapes/ui/tree_render.py` (`compute_dest` or new `render_dest` function)
- Test: `tests/test_ui/test_tree_render.py`

**Step 1: Add `render_dest` function**

```python
def render_dest(dest: str | None) -> Text:
    """Render destination with dim directory, normal stem, dim extension."""
    if dest is None:
        return Text("???", "dim")

    text = Text()
    text.append("→ ", "dim")

    if "?" in dest and "/" not in dest:
        # Unresolved destination
        text.append("?", "yellow")
        return text

    last_slash = dest.rfind("/")
    if last_slash >= 0:
        # Directory part: dim
        text.append(dest[:last_slash + 1], "dim")
        filename = dest[last_slash + 1:]
    else:
        filename = dest

    # Split stem from extension
    dot = filename.rfind(".")
    if dot > 0:
        text.append(filename[:dot])  # stem: normal (default fg)
        text.append(filename[dot:], "dim")  # extension: dim
    else:
        text.append(filename)

    return text
```

**Step 2: Integrate into render_file_row**

After the filename, append the styled destination:

```python
dest = compute_dest(node, template)
text.append("  ")
text.append_text(render_dest(dest))
```

**Step 3: Handle unresolved fields with yellow `?`**

When `compute_dest` returns a string containing `?` placeholders for missing fields, the `?` characters should be yellow. Adjust `render_dest` to detect and style `?` within a partially resolved path.

**Step 4: Write tests**

```python
def test_render_dest_dim_directory():
    result = render_dest("Movies/Inception (2010)/Inception (2010).mkv")
    # Verify directory part is dim, stem is normal, extension is dim

def test_render_dest_no_directory():
    result = render_dest("Inception (2010).mkv")
    # Verify stem normal, extension dim

def test_render_dest_unresolved():
    result = render_dest(None)
    # Returns "???" dim

def test_render_dest_yellow_question():
    result = render_dest("?")
    # Yellow ?
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_render.py -v`

**Step 6: Commit**

```
feat: destination path coloring — dim directory, normal stem
```

---

## Task 5: Detail View — One Source at a Time

Replace the multi-column grid with a two-column layout: result on left, one source on right. `h/l` cycles through sources. The `cursor_col` concept changes — it no longer navigates columns, it selects which source to display.

**Files:**
- Modify: `tapes/ui/detail_view.py` (major refactor of rendering and cursor logic)
- Modify: `tapes/ui/detail_render.py` (new rendering helpers)
- Test: `tests/test_ui/test_detail_view.py`, `tests/test_ui/test_detail_render.py`

**Step 1: Replace cursor_col with source_index**

In `detail_view.py`:

```python
# Remove: cursor_col: reactive[int] = reactive(0)
# Add:
source_index: reactive[int] = reactive(0)  # which TMDB source to display
```

The detail view always shows two columns: result (left) and current source (right). `h` decrements `source_index`, `l` increments. Clamp to `[0, len(sources) - 1]`.

**Step 2: Rewrite grid rendering**

Replace `_render_grid_header` and `_render_field_row` to show exactly two columns:

```
             result                    TMDB #1 (92%)              [1/2]
─────────────────────────────────────────────────────────────────────────
 title       Inception                 Inception
 year        2010                      2010
 media_type  movie                     movie
 codec       x264                      ·
```

Use wider columns since we have only two. `LABEL_WIDTH = 14`, result column and source column each get roughly half the remaining width.

In `detail_render.py`:

```python
def render_detail_grid_one_source(
    node: FileNode,
    source: Source | None,
    source_index: int,
    total_sources: int,
    fields: list[str],
    cursor_row: int,
) -> Text:
    """Render result vs one source side by side."""
    ...
```

**Step 3: Update cursor navigation**

- `j/k` moves `cursor_row` between field rows (unchanged behavior).
- `h/l` changes `source_index` (was `cursor_col`).
- `enter` applies field from current source to result (unchanged behavior, but always from `sources[source_index]`).
- `shift+enter` applies all fields from current source.

**Step 4: Update _render_field_row for two-column layout**

Each field row shows: label, result value, source value. Result value is always bold/white. Source value uses diff highlighting (Task 6 adds colors, this step just gets the layout right).

**Step 5: Update existing tests**

Many tests reference `cursor_col`. Update to use `source_index`. Tests for grid rendering need updated expected output (two columns instead of N columns).

**Step 6: Run tests**

Run: `uv run pytest tests/test_ui/test_detail_view.py -v`

**Step 7: Commit**

```
feat: one-source-at-a-time detail view with h/l cycling
```

---

## Task 6: Detail View Diff Highlighting

Source values colored relative to the result: dim (matches), yellow (differs), green (fills empty).

**Files:**
- Modify: `tapes/ui/detail_render.py` (new `diff_style` function)
- Modify: `tapes/ui/detail_view.py` (apply styles in field rows)
- Test: `tests/test_ui/test_detail_render.py`

**Step 1: Add diff_style function**

```python
def diff_style(result_val: Any, source_val: Any) -> str:
    """Return Rich style for a source value relative to the result."""
    if source_val is None:
        return "dim"  # missing in source → dim ·
    if result_val is None or result_val == "":
        return "green"  # fills empty slot
    if str(result_val) == str(source_val):
        return "dim"  # matches result
    return "yellow"  # differs from result
```

**Step 2: Apply in field row rendering**

When rendering source column values, apply `diff_style`:

```python
style = diff_style(result_val, source_val)
text.append(display_val(source_val), style)
```

Result column values always use bold white:

```python
text.append(display_val(result_val), "bold white")
```

**Step 3: Add confidence coloring**

In the source header (`TMDB #1 (92%)`):
- Source label: blue
- Confidence >= 0.8: green
- Confidence 0.5-0.79: yellow
- Confidence < 0.5: red

```python
def confidence_style(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"
```

**Step 4: Write tests**

```python
def test_diff_style_matches():
    assert diff_style("Inception", "Inception") == "dim"

def test_diff_style_differs():
    assert diff_style("Inception", "Inception Man") == "yellow"

def test_diff_style_fills_empty():
    assert diff_style(None, "Inception") == "green"

def test_diff_style_missing_source():
    assert diff_style("Inception", None) == "dim"

def test_confidence_style():
    assert confidence_style(0.92) == "green"
    assert confidence_style(0.65) == "yellow"
    assert confidence_style(0.38) == "red"
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_detail_render.py -v`

**Step 6: Commit**

```
feat: diff highlighting and confidence coloring in detail view
```

---

## Task 7: Compact Detail Preview

When tree is focused, the detail panel shows a 2-line compact preview of the hovered file. For folders, show a summary.

**Files:**
- Modify: `tapes/ui/detail_view.py` (add compact render path)
- Modify: `tapes/ui/detail_render.py` (new `render_compact_preview` function)
- Modify: `tapes/ui/tree_app.py` (update detail on cursor move)
- Test: `tests/test_ui/test_detail_render.py`

**Step 1: Add render_compact_preview for files**

```python
def render_compact_preview(node: FileNode, template: str) -> Text:
    """Two-line compact preview: filename + dest, key fields + confidence."""
    text = Text()
    # Line 1: filename → destination
    text.append(node.path.name, "bold white")
    text.append("  ")
    text.append_text(render_dest(compute_dest(node, template)))
    text.append("\n")

    # Line 2: key fields + TMDB confidence
    fields = ["title", "year", "media_type", "season", "episode"]
    parts = []
    for f in fields:
        short = {"title": "title", "year": "year", "media_type": "type",
                 "season": "S", "episode": "E"}[f]
        val = node.result.get(f)
        parts.append(Text.assemble((f"{short}: ", "dim"), display_val(val)))
    # Join with double space
    for i, part in enumerate(parts):
        if i > 0:
            text.append("  ")
        text.append_text(part)

    # TMDB confidence (best source)
    if node.sources:
        best = max(node.sources, key=lambda s: s.confidence)
        conf = best.confidence
        style = confidence_style(conf)
        text.append(f"  TMDB ", "blue")
        text.append(f"{conf:.0%}", style)

    return text
```

**Step 2: Add render_compact_preview for folders**

```python
def render_folder_preview(folder: FolderNode) -> Text:
    """Summary line for folder: file count, unstaged count, ignored count."""
    files = [c for c in folder.children if isinstance(c, FileNode)]
    unstaged = sum(1 for f in files if not f.staged and not f.ignored)
    ignored = sum(1 for f in files if f.ignored)
    text = Text()
    text.append(f"{folder.name}/\n", "bold white")
    parts = [f"{len(files)} files"]
    if unstaged:
        parts.append(f"{unstaged} unstaged")
    if ignored:
        parts.append(f"{ignored} ignored")
    text.append(" · ".join(parts), "dim")
    return text
```

**Step 3: Update DetailView.render() to branch on expanded state**

```python
def render(self) -> RenderableType:
    if self.has_class("expanded"):
        return self._render_full()  # existing full grid rendering
    else:
        return self._render_compact()  # compact 2-line preview
```

**Step 4: Update TreeApp to feed hovered node to DetailView on cursor move**

In `tree_app.py`, watch cursor changes and update the detail view:

```python
def watch_cursor(self) -> None:
    tree = self.query_one(TreeView)
    node = tree.current_node
    if node:
        detail = self.query_one(DetailView)
        detail.set_preview_node(node)
```

**Step 5: Write tests for compact preview**

Test that the compact preview contains filename, destination, key fields, and confidence percentage.

**Step 6: Run tests**

Run: `uv run pytest tests/test_ui/ -v`

**Step 7: Commit**

```
feat: compact 2-line detail preview when tree is focused
```

---

## Task 8: Context-Aware Footer

Single footer row showing relevant shortcuts for the current view. Keybinding hints in cyan.

**Files:**
- Modify: `tapes/ui/tree_app.py` (footer rendering logic)
- Test: `tests/test_ui/test_tree_app.py`

**Step 1: Replace Textual Footer with custom Static widget**

Textual's built-in Footer auto-generates from bindings. Replace with a custom Static that we control:

```python
class StatusFooter(Static):
    """Context-aware footer showing relevant keybindings."""
    mode: reactive[str] = reactive("tree")

    def render(self) -> RenderableType:
        if self.mode == "edit":
            return self._edit_footer()
        elif self.mode == "detail":
            return self._detail_footer()
        else:
            return self._tree_footer()

    def _tree_footer(self) -> Text:
        return Text.assemble(
            " ", ("space", "cyan"), " stage  ",
            ("enter", "cyan"), " detail  ",
            ("a", "cyan"), " accept  ",
            ("c", "cyan"), " commit  ",
            ("?", "cyan"), " help",
        )

    def _detail_footer(self) -> Text:
        return Text.assemble(
            " ", ("enter", "cyan"), " apply  ",
            ("⇧enter", "cyan"), " apply all  ",
            ("h/l", "cyan"), " sources  ",
            ("esc", "cyan"), " back  ",
            ("?", "cyan"), " help",
        )

    def _edit_footer(self) -> Text:
        return Text.assemble(
            " ", ("enter", "cyan"), " confirm  ",
            ("esc", "cyan"), " cancel",
        )
```

**Step 2: Update tree_app compose and state transitions**

Replace `yield Footer()` with `yield StatusFooter(id="footer")`. Update `_enter_detail`, `_leave_detail`, `_start_edit`, `_commit_edit` to set `footer.mode`.

**Step 3: Add CSS for footer**

```css
StatusFooter {
    dock: bottom;
    height: 1;
    background: $surface;
}
```

**Step 4: Write tests**

Test that footer content changes when toggling between tree/detail/edit modes.

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py -v`

**Step 6: Commit**

```
feat: context-aware footer with styled keybinding hints
```

---

## Task 9: Help Overlay

Press `?` to show a centered bordered modal with all shortcuts and concept explanations. Close with `?` or `esc`.

**Files:**
- Create: `tapes/ui/help_overlay.py`
- Modify: `tapes/ui/tree_app.py` (add `?` binding, compose overlay)
- Test: `tests/test_ui/test_help_overlay.py`

**Step 1: Create HelpOverlay widget**

```python
class HelpOverlay(Static):
    """Centered modal with keybinding reference and concept explanations."""

    def render(self) -> RenderableType:
        # Build bordered content with box-drawing characters
        # Two sections: Files shortcuts, Detail shortcuts
        # Plus concept explanations (staged, unstaged, ignored, sources)
        ...
```

Content from the design spec (section "Help Overlay"):
- Files: j/k navigate, enter detail/toggle, space stage, a accept, x ignore, c commit, v select, / search, ` flat/tree, -/= collapse/expand, r refresh, u undo
- Detail: j/k fields, h/l sources, enter apply, shift+enter apply all, e edit, d clear, D reset, r re-query, u undo, esc back
- Concepts: ✓ staged, ○ unstaged, · ignored, sources explanation

**Step 2: Add to tree_app compose**

```python
def compose(self) -> ComposeResult:
    yield TreeView(id="tree")
    yield DetailView(id="detail")
    yield HelpOverlay(id="help")  # initially hidden
    yield StatusFooter(id="footer")
```

CSS: `HelpOverlay { display: none; layer: overlay; }` and `.show-help HelpOverlay { display: block; }`

**Step 3: Add `?` keybinding**

```python
("question_mark", "toggle_help", "Help"),
```

```python
def action_toggle_help(self) -> None:
    self.toggle_class("show-help")
```

**Step 4: Write tests**

Test that `?` shows the overlay, `?` again hides it, `esc` hides it. Test that overlay contains expected keybinding text.

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_help_overlay.py -v`

**Step 6: Commit**

```
feat: help overlay with keybinding reference
```

---

## Task 10: Commit Modal

Press `c` to show a bordered confirmation modal listing staged files with destinations. `y` confirms, `n` cancels.

**Files:**
- Create: `tapes/ui/commit_modal.py`
- Modify: `tapes/ui/tree_app.py` (refactor commit flow to use modal)
- Test: `tests/test_ui/test_commit_modal.py`

**Step 1: Create CommitModal widget**

```python
class CommitModal(Static):
    """Confirmation dialog for committing staged files."""

    def __init__(self, staged_files: list[tuple[str, str]], operation: str):
        """staged_files: list of (filename, destination) tuples."""
        super().__init__()
        self.staged_files = staged_files
        self.operation = operation

    def render(self) -> RenderableType:
        # Box-drawing bordered modal:
        # ┌─ Commit ─────────────────────┐
        # │                               │
        # │  Copy N files to library?     │
        # │                               │
        # │  ✓ filename.mkv               │
        # │    → destination/path.mkv     │
        # │  ...                          │
        # │                               │
        # │  y confirm    n cancel        │
        # │                               │
        # └───────────────────────────────┘
        ...
```

**Step 2: Integrate into tree_app**

Replace the current `_confirming_commit` state with a modal widget approach. Add CommitModal to compose (hidden by default). Show on `c`, handle `y`/`n` to confirm/cancel.

**Step 3: Apply background dimming**

When modal is visible, add a CSS class that dims the tree and detail panels:

```css
.modal-open TreeView { opacity: 0.3; }
.modal-open DetailView { opacity: 0.3; }
```

**Step 4: Write tests**

Test that `c` shows modal with correct file count, `y` triggers processing, `n` closes modal. Test that staged file list appears in modal content.

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_commit_modal.py -v`

**Step 6: Commit**

```
feat: styled commit confirmation modal
```

---

## Task 11: Multi-File Detail View

When multiple files are selected and user enters detail view, show shared fields with `(N values)` for differences. TMDB query uses shared values.

This mostly exists already (M15), but needs updating for the one-source-at-a-time layout and diff highlighting.

**Files:**
- Modify: `tapes/ui/detail_view.py` (update multi-file rendering for new layout)
- Modify: `tapes/ui/detail_render.py` (shared field rendering)
- Test: `tests/test_ui/test_detail_view.py`

**Step 1: Update multi-file header**

In the new one-source-at-a-time layout, the header shows `N files selected` instead of a filename:

```python
def _render_multi_header(self) -> Text:
    text = Text()
    text.append(f"{len(self._file_nodes)} files selected", "bold white")
    return text
```

**Step 2: Ensure shared field computation works with new rendering**

The existing `compute_shared_fields()` in `tree_model.py` returns shared values or `"(N values)"` markers. Verify this works with the two-column layout (result column shows shared values, source column shows TMDB source).

**Step 3: Update diff highlighting for shared fields**

When a shared field shows `(N values)`, the source diff should compare against the shared value (or show no diff if mixed).

**Step 4: Update tests**

Adapt multi-file tests to the new one-source-at-a-time layout.

**Step 5: Run tests**

Run: `uv run pytest tests/test_ui/test_detail_view.py -v -k multi`

**Step 6: Commit**

```
feat: multi-file detail view with one-source-at-a-time layout
```

---

## Task 12: Final Polish and Integration Tests

Wire everything together, verify all visual states match the design spec.

**Files:**
- Modify: `tapes/ui/tree_app.py` (final CSS cleanup, ensure all states work)
- Test: `tests/test_ui/test_tree_app.py` (integration tests)

**Step 1: Remove dead code**

Remove the old Header widget reference, old Static #status widget, any remnants of the multi-column grid detail view, old footer logic.

**Step 2: Verify all keybindings work end-to-end**

Write integration tests using Textual Pilot that exercise:
1. Launch → tree view with borders, colored markers, styled destinations
2. `j/k` navigation updates compact preview
3. `enter` opens detail view (panel expansion, border color change)
4. `h/l` cycles sources in detail view
5. `enter` applies field, destination updates
6. `esc` returns to tree
7. `?` shows help overlay, `?` closes it
8. `c` shows commit modal, `n` cancels
9. `/` search mode

**Step 3: CSS final pass**

Ensure:
- Panel borders are clean at various terminal sizes
- Scrolling works within bordered panels
- Compact preview truncates cleanly
- No visual glitches at small terminal sizes

**Step 4: Run full test suite**

Run: `uv run pytest -v`

All 381+ tests should pass.

**Step 5: Commit**

```
feat: visual design integration polish
```

---

## Dependency Order

```
Task 1 (layout) ──→ Task 2 (borders) ──→ Task 3 (tree colors) ──→ Task 4 (dest coloring)
                                      └──→ Task 5 (detail redesign) ──→ Task 6 (diff highlight)
                                                                    └──→ Task 11 (multi-file)
Task 1 ──→ Task 7 (compact preview)
Task 1 ──→ Task 8 (footer)
Task 2 ──→ Task 9 (help overlay)
Task 2 ──→ Task 10 (commit modal)
All tasks ──→ Task 12 (polish)
```

Tasks 3, 4, 5, 7, 8 can proceed in parallel once Tasks 1-2 are done.
Tasks 9, 10 can proceed in parallel once Task 2 is done.
Task 6 needs Task 5. Task 11 needs Task 5.
Task 12 is last.
