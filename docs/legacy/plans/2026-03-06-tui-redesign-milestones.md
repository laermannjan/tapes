# TUI Redesign: Implementation Milestones

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the TUI from a spreadsheet grid into a lazygit-inspired file
tree with drill-in detail view, staging, and source-based metadata curation.

**Design spec:** `docs/plans/2026-03-06-tui-redesign.md`

---

## Refactor vs. Rewrite

**Decision: Rewrite the UI from scratch.**

Reasoning:

1. **Fundamentally different interaction model.** The current grid is a
   spreadsheet with cell-level crosshair cursor, column navigation, inline
   editing. The new design is a lazygit-style file tree with full-row
   highlight, folder collapse/expand, staging markers, and a drill-in
   detail view.

2. **Models are not reusable.** `GridRow` conflates view state with metadata.
   The new design needs a `FileNode` with staging state, a `result` dict, and
   a list of `Source` objects. `RowKind`, `RowStatus` have no analogues.

3. **Rendering is entirely different.** Fixed-width column rendering with
   cell-level cursor coloring vs. tree indentation with unicode arrows and
   staging markers.

4. **Tests assert the old interaction model.** Every test checks cell-level
   cursor positions, column selection, inline edit buffers. None are adaptable.

5. **Reusable pieces are small.** `dest.py` (59 lines) for template rendering
   and `query.py` (49 lines) for mock TMDB are kept. Everything else is new.

---

## Milestones

### M1: Data model and tree building

**Delivers:** `FileNode`, `FolderNode`, `TreeModel` with staging state, result
metadata, and sources. No rendering -- pure data structures and tests.

**Files:**
- Create: `tapes/ui/tree_model.py`
- Test: `tests/test_ui/test_tree_model.py`

**Tasks:**
- `FileNode` dataclass: path, staged, ignored, result (dict), sources (list of Source)
- `Source` dataclass: name, fields (dict), confidence (float)
- `FolderNode`: name, children, collapsed
- `TreeModel`: root folder, flat iteration (respecting collapse), toggle staged/ignored, toggle folder collapse
- `build_tree(groups, root_path) -> TreeModel`
- `flatten(model) -> list[FileNode | FolderNode]`
- `(various)` computation for multi-selection shared fields

---

### M2: Tree view rendering (static)

**Delivers:** Textual widget that renders the file tree as styled text. No
cursor yet -- visual output only.

**Files:**
- Create: `tapes/ui/tree_render.py`
- Create: `tapes/ui/tree_view.py`
- Test: `tests/test_ui/test_tree_render.py`

**Tasks:**
- Render `FileNode` row: staging marker, filename, arrow, destination path
- Render `FolderNode` row: `▶`/`▼` arrow + folder name
- Tree mode indentation (2 spaces per level)
- Flat mode: no indentation, relative paths
- Use `dest.py` for destination computation
- `TreeView` widget takes `TreeModel`, calls `flatten()`, renders rows

---

### M3: Cursor navigation

**Delivers:** Full-row highlight cursor, `j/k`/arrows move, `enter` toggles
folder collapse, `q` quits. First interactive milestone.

**Files:**
- Create: `tapes/ui/tree_app.py`
- Modify: `tapes/ui/tree_view.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- `TreeApp` composes header, `TreeView`, footer
- Cursor tracks index into flattened list
- `j/k`/arrows move cursor, full-row highlight
- `enter` on folder toggles collapse, re-flattens, adjusts cursor
- `q` quits (confirm if staged files exist)
- Scroll viewport to keep cursor visible
- Wire CLI `grid` command to `TreeApp` for dev iteration

---

### M4: Staging toggle

**Delivers:** `space` toggles staged/unstaged. Visual markers update. Footer
shows staged count.

**Files:**
- Modify: `tapes/ui/tree_app.py`, `tapes/ui/tree_view.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- `space` on file toggles `staged` flag
- `space` on folder toggles all children recursively
- Footer shows `N staged / M total`
- Staging markers update immediately

---

### M5: Range selection

**Delivers:** `v` enters range select, cursor movement extends selection,
`space` stages/unstages range, `esc` clears.

**Files:**
- Modify: `tapes/ui/tree_app.py`, `tapes/ui/tree_view.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- `v` sets anchor at cursor, starts range mode
- `j/k` extends contiguous selection from anchor to cursor
- Selected rows get distinct background
- `space` stages/unstages entire selection
- `esc` or `v` again exits range mode

---

### M6: Detail view -- static rendering

**Delivers:** `enter` on file drills into detail view showing result and source
columns. No editing yet.

**Files:**
- Create: `tapes/ui/detail_view.py`
- Create: `tapes/ui/detail_render.py`
- Test: `tests/test_ui/test_detail_view.py`

**Tasks:**
- Header: filename and computed destination
- Field rows: one per template-required field
- Columns: result (left of `┃`), then sources
- Source confidence in header
- Empty values as `·`
- `esc` returns to tree view

---

### M7: Detail view -- cursor and source application

**Delivers:** `h/j/k/l` navigates the grid. `enter` on source field copies to
result. `enter` on source header applies all non-empty fields.

**Files:**
- Modify: `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`
- Test: `tests/test_ui/test_detail_view.py`

**Tasks:**
- Cell-level cursor (row = field, col = result or source)
- `enter` on result column: inline edit
- `enter` on source field: copy value to result
- `enter` on source header: apply all non-empty fields
- `shift-enter` on source header: apply all fields including clearing empties
- Destination updates live

---

### M8: Auto-pipeline on startup

**Delivers:** Pipeline runs automatically: guessit fills result, TMDB populates
sources, confident matches auto-accept and auto-stage.

**Files:**
- Modify: `tapes/ui/tree_app.py`, `tapes/ui/tree_model.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- Populate `from filename` source from guessit metadata
- Query mock TMDB per file, populate `TMDB #N` sources
- Auto-accept confident matches (non-empty fields to result)
- Auto-stage confident files
- Progress indicator during pipeline

---

### M9: Accept best match (`a`)

**Delivers:** `a` in tree view applies highest-confidence TMDB match to result
regardless of confidence level.

**Files:**
- Modify: `tapes/ui/tree_app.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- `a` on cursor: apply best TMDB source to result (non-empty only)
- `a` on selection: apply per file individually
- No-op if no TMDB sources

---

### M10: Refresh (`r`)

**Delivers:** `r` re-queries TMDB. Per-file in tree, shared query in detail.

**Files:**
- Modify: `tapes/ui/tree_app.py`, `tapes/ui/detail_view.py`
- Test: `tests/test_ui/test_tree_app.py`, `tests/test_ui/test_detail_view.py`

**Tasks:**
- Tree `r`: re-query per file using each file's own result values
- Detail `r`: query once using shared result values (omit `(various)`)
- Update source columns with new results
- Auto-accept confident matches

---

### M11: Undo (`u`)

**Delivers:** `u` reverts the last metadata change.

**Files:**
- Modify: `tapes/ui/tree_model.py`, `tapes/ui/tree_app.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- Snapshot affected nodes before every mutation
- `u` restores most recent snapshot
- Single-level undo

---

### M12: Ignore (`x`) and commit (`c`)

**Delivers:** `x` marks file as ignored. `c` opens process confirmation.

**Files:**
- Modify: `tapes/ui/tree_app.py`, `tapes/ui/tree_view.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- `x` toggles ignored on cursor/selection
- Ignored files rendered dimmed, no marker
- `c` shows confirmation: count, operation, dry-run
- `enter` confirms, `esc` cancels
- Blocked if no staged files

---

### M13: Flat/tree toggle (`` ` ``)

**Delivers:** Backtick toggles between tree and flat display modes.

**Files:**
- Modify: `tapes/ui/tree_view.py`, `tapes/ui/tree_app.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- Backtick toggles `flat_mode` flag
- Flat: all files without folder nodes, relative paths
- Tree: normal hierarchy with folders
- Cursor stays on same file across toggle

---

### M14: Fuzzy search (`/`)

**Delivers:** `/` enters search mode, typing filters tree to matching files.

**Files:**
- Create: `tapes/ui/search.py`
- Modify: `tapes/ui/tree_app.py`
- Test: `tests/test_ui/test_tree_app.py`

**Tasks:**
- `/` shows text input at bottom
- Typing filters to matching filenames (case-insensitive)
- `enter` jumps to first match
- `esc` clears filter, shows full tree
- Folders auto-expand if containing matches

---

### M15: Multi-file detail view

**Delivers:** `enter` on selection opens detail view with `(various)` for
differing values.

**Files:**
- Modify: `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`
- Test: `tests/test_ui/test_detail_view.py`

**Tasks:**
- Header: "N files selected", "(various destinations)"
- Shared values shown, differing show `(various)`
- Editing applies to all files
- Applying source applies to all files
- `r` uses shared (non-various) values

---

### M16: CLI integration and old UI cleanup

**Delivers:** New TUI is the default. Old UI files removed.

**Files:**
- Modify: `tapes/cli.py`
- Remove: `tapes/ui/grid.py`, `tapes/ui/models.py`, `tapes/ui/render.py`,
  `tapes/ui/edit_modal.py`, `tapes/ui/app.py`, `tapes/ui/split_modal.py`,
  `tapes/ui/merge_modal.py`, `tapes/ui/file_editor.py`
- Remove: old test files

**Tasks:**
- Wire `tapes import` to `TreeApp`
- Wire `tapes grid` dev command to `TreeApp`
- Remove old UI code and tests
- Verify all remaining tests pass
