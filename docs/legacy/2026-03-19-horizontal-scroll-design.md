# Horizontal Scroll for Tree View

## Problem

Long filenames and destination paths get truncated at the viewport edge.
Users cannot see the full destination, which makes it hard to verify
correctness before staging.

## Design

Add horizontal scrolling to the tree view, matching the existing vertical
scroll model. All rows shift together, preserving arrow column alignment.

### Behavior

- **Shift+left / Shift+right** scroll the viewport horizontally by 4
  characters per keystroke.
- The horizontal offset persists across vertical cursor movement and
  vertical scrolling. It resets to 0 on tree rebuilds (folder toggle,
  flat mode toggle, filter changes) to match the vertical scroll behavior.
- Clamp at 0 on the left. Clamp on the right at `max_row_width -
  viewport_width` so the user cannot scroll into empty space. Compute
  `max_row_width` from the visible rows during render.

### Rendering pipeline

1. Render each row at full natural width (no truncation, no padding).
   Remove the current `row_text.truncate(inner_width)` call.
2. Slice the row from `h_offset` to `h_offset + inner_width`.
3. Add `…` indicators where content was clipped (see below).
4. Pad the sliced row to `inner_width` with spaces for cursor/range
   highlighting.

### Indicators

Each row independently shows a `…` character where its content is clipped:

- Leading `…` on the left if that row has content before the viewport.
- Trailing `…` on the right if that row extends beyond the viewport.
- Rows that fit entirely at the current offset show no indicators.

The `…` replaces the first or last visible character of the row, so the
total row width stays constant.

### Vertical scroll indicators

The existing "↑ more above" / "↓ more below" indicator rows are
navigational chrome, not content. They render at fixed position and are
not subject to horizontal offset.

### Interaction with arrow column

The arrow column (`arrow_col`) aligns all `→` markers. Because horizontal
scroll shifts every row by the same offset, alignment is preserved. No
changes to `_compute_arrow_col()` are needed.

### Resize

`on_resize` already recomputes `arrow_col`. It should also clamp
`_h_scroll_offset` to the new maximum (which may be smaller if the
terminal grew wider).

## Files

- `tapes/ui/tree_view.py` - add `_h_scroll_offset`, add
  `scroll_horizontal(delta)` method, modify `render()` per the pipeline
  above, clamp on resize
- `tapes/ui/tree_render.py` - no changes (rows already render at full
  width; truncation happens in tree_view)
- `tapes/ui/tree_app.py` - handle shift+left/right in `on_key()` by
  calling `tree_view.scroll_horizontal()`, alongside the existing
  left/right folder collapse/expand handling

## Limitations

- East Asian wide characters (CJK filenames) may cause alignment issues
  since `…` is single-width. Not expected for this project.

## Out of scope

- Horizontal scroll in metadata view, commit view, or help view.
- Scroll position indicator in the bottom bar.
- Home/End for horizontal scroll.
