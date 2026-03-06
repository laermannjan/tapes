# M7: Shift+E Edit Modal

## Overview

A centered modal overlay for editing all metadata fields at once, replacing
the single-field inline edit (`e`) for bulk or detailed editing workflows.

## Trigger

`Shift+E` opens the modal. Scope is `_target_rows()` -- the cursor row, or
all selected rows if a selection is active. Disabled in dest mode.

## Layout

Centered overlay panel with a vertical form. One field per row, label
left-aligned, value to the right. Fixed field set:

```
+-- Edit metadata ---------------------+
|  title:          Breaking Bad         |
|  year:           2008                 |
|  season:         1                    |
|  episode:        (various)            |
|  episode_title:  [cursor here]        |
|                                       |
|  tab: next  shift-tab: prev           |
|  f: freeze  enter: ok  esc: cancel   |
+---------------------------------------+
```

Fields: `title`, `year`, `season`, `episode`, `episode_title`.

## Field states

- **Normal:** editable, shows current value from first target row.
- **Frozen:** dimmed/greyed, typing ignored until unfrozen with `f`.
- **Various:** multi-selection where target rows have differing values.
  Shows `(various)` as placeholder text (not a real value).

## Navigation and keys

| Key | Action |
|-----|--------|
| `tab` | Move to next field (wraps, includes frozen fields) |
| `shift-tab` | Move to previous field (wraps) |
| `f` | Toggle freeze on focused field |
| `enter` | Commit all changes, close modal |
| `esc` | Discard all changes, close modal |
| typing | Edit focused field value |
| `backspace` | Delete last character |

## Various-field behavior

`(various)` is virtual placeholder text, not an editable value.

- Pressing `enter` without modifying the field: no-op (value unchanged).
- Pressing any character or `backspace`: placeholder disappears, user starts
  from a blank value.
- If user types then clears back to empty: field is set to empty string
  (distinct from untouched).

## Commit behavior

- Atomic: `esc` discards everything, `enter` applies everything.
- Only fields the user actually modified get applied to target rows.
- Untouched `(various)` fields are skipped entirely.
- Frozen fields cannot be modified (typing is ignored).
- Applied as a single undoable operation (`u` after closing).
- Int fields (`year`, `season`, `episode`) are validated on commit;
  invalid values cancel that field silently.

## Scope

- Works on `_target_rows()`: cursor row or selected rows.
- Multi-selection: initial values come from first target row; differing
  values show `(various)`.
- All changes apply to every target row.
