# Arrow key navigation and space toggle in edit companions

**Date:** 2026-03-05
**Type:** Enhancement
**Status:** Superseded by #007 (adopt prompt_toolkit)
**Component:** `tapes/importer/interactive.py` -- `edit_companions`

---

## Current behavior

The edit companions checklist uses single-digit number keys (0-9) to toggle
files. This limits the list to 10 items and requires the user to visually map
numbers to entries.

## Proposed behavior

Replace the digit-based toggle with a cursor-based interface:

- **Up/Down arrow keys** (or `j`/`k`) move a visible cursor through the list.
- **Space** toggles the selected item.
- **Enter** confirms and exits.
- Video files remain locked (cannot be toggled).

The cursor position should be visually indicated (e.g., `>` prefix or
highlight). This removes the 10-item limit and is more intuitive for
terminal-native users.

## Implementation notes

- Arrow keys emit multi-byte escape sequences (`\033[A`, `\033[B`). The
  `_read_key` function currently reads a single byte -- it needs to detect the
  `\033` prefix and read the full sequence.
- Consider using Rich's `Live` display for flicker-free re-rendering instead of
  the current `_clear_lines` approach, since cursor movement requires frequent
  redraws.
- The `j`/`k` bindings are optional but cheap to add and match vim conventions.

## Acceptance criteria

- [ ] Arrow keys move cursor through companion list
- [ ] Space toggles the item at cursor
- [ ] Enter confirms selection
- [ ] Video files cannot be toggled (cursor skips or shows locked indicator)
- [ ] Works with lists longer than 10 items
- [ ] Existing tests updated, new tests for cursor movement
