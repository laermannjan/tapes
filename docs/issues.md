# Issue Tracker

Status labels: `open` | `in-progress` | `done`

Design doc: `docs/plans/2026-03-08-detail-view-redesign.md`

---

## I01: Modal background color incorrect
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/commit_modal.py`, `tapes/ui/help_overlay.py`

The modal panels use `background: #1a1a2e` in their CSS. This creates visible
contrast against the terminal background. Should inherit terminal bg instead.

**Decision log:**
- Remove explicit `background` from modal CSS. The `textual-ansi` theme handles transparency.

---

## I02: Detail view columns always split 50/50
**Status:** `done`
**Severity:** visual / layout
**Files:** `tapes/ui/detail_view.py`

The detail view splits columns 50/50. All three column areas (field names,
values, source values) should auto-size based on longest content + padding.

**Decision log:**
- Auto-size all three columns. Measure longest field name, longest value, longest source value.
- Subsumes I03 (padding) and I04 (separator). No vertical separator, use whitespace.

---

## I03: Detail view field name padding is incorrect
**Status:** `done` (subsumed by I02)
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Fixed label width of 16 doesn't adapt to actual field name lengths.

**Decision log:**
- Handled by I02 auto-sizing. Label column width = longest field name + padding.

---

## I04: Detail view column separator looks thick
**Status:** `done` (subsumed by redesign)
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`

The `┃` separator renders too thick.

**Decision log:**
- Eliminated entirely. Use 3+ spaces between columns (Claude Code style). No vertical separators.

---

## I05: tmdb_id field missing from detail view
**Status:** `done`
**Severity:** functional
**Files:** `tapes/ui/detail_render.py`

`tmdb_id` is not in the template so it never appears in the grid.

**Decision log:**
- Inject `tmdb_id` as the first field in `get_display_fields()`, always.

---

## I06: Detail view column headers don't look like headers
**Status:** `done` (subsumed by redesign)
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`

Headers look like regular field values.

**Decision log:**
- Replaced by tab-based design. "Info" as window title in purple. TMDB sources
  as tabs (active = inverted, inactive = default white). No "result" header;
  field names and editable values have no column label.

---

## I07: File path missing in detail view
**Status:** `done`
**Severity:** functional
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Only filename shown, not full relative path.

**Decision log:**
- Show full path relative to scan root. Same styling as tree view row.

---

## I08: Detail view dimming inconsistent with tree view
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`

Filename/destination styling in detail header doesn't match tree view rows.

**Decision log:**
- Use identical styling: filename normal, arrow muted, destination via `render_dest()`.

---

## I09: Tree view should dim when detail view is focused
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/tree_app.py`, `tapes/ui/tree_view.py`

Tree stays full contrast when detail is focused.

**Decision log:**
- Add CSS or class toggle to dim tree content when detail is expanded.
  Use muted color (~`#555555`) for all tree text when unfocused.

---

## I10: Inline editing doesn't work
**Status:** `done`
**Severity:** critical / functional
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/tree_app.py`

Edit mode only triggers when no sources exist. Raw text accumulator is fragile.

**Decision log:**
- Rework as part of detail view redesign. `Enter` on a field in the left column
  (editable values) starts inline edit. When sources exist, `Enter` edits (not
  applies). Applying from source tab uses a different key or workflow. Consider
  Textual Input widget for proper text editing.

---

## I11: Commit modal should show operation selection, not file list
**Status:** `done`
**Severity:** UX / functional
**Files:** `tapes/ui/commit_modal.py`, `tapes/ui/tree_app.py`

Modal lists all staged files redundantly.

**Decision log:**
- Replace with: file count + operation selector (cycle: copy/move/link/hardlink).
- `h/l` or `←/→` to cycle operation. Default from config.
- Returns (confirmed: bool, operation: str).

---

## I12: Missing values inconsistently shown as dot vs question mark
**Status:** `done`
**Severity:** visual consistency
**Files:** `tapes/ui/detail_render.py`

`display_val()` returns `·` for None, but destinations use `?`.

**Decision log:**
- Always `?`. Change `display_val()` and audit all `\u00b7` usage in render code.

---

## I13: Focused detail view header should be one line
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Filename and destination on separate lines wastes vertical space.

**Decision log:**
- Single line: `path/to/file.mkv → destination`. Same format as tree view rows.

---

## I14: Unfocused detail view shows too much metadata
**Status:** `done`
**Severity:** UX
**Files:** `tapes/ui/detail_render.py`

Compact preview dumps title, year, type, season, episode.

**Decision log:**
- Show only: `tmdb: {id}  {confidence}%`. Confidence only when tmdb_id is set.
  If no tmdb_id: `tmdb: ?`.

---

## I15: Editing a metadata field should clear tmdb_id
**Status:** `done`
**Severity:** functional
**Files:** `tapes/ui/detail_view.py`

Manual edit doesn't invalidate the TMDB identification.

**Decision log:**
- `_commit_edit()` removes `tmdb_id` from result (unless editing tmdb_id itself).

---

## I16: TMDB blue and confidence green clash visually
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Blue TMDB label + green confidence look discordant.

**Decision log:**
- TMDB label: default white (not colored). Active tab is inverted with accent color.
- Confidence >=80%: muted. 50-79%: ember. <50%: red.
- Only the match indicator `[1/3]` uses accent color (via tab design).

---
