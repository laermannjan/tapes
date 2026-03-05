# Fuzzy search filter in edit companions

**Date:** 2026-03-05
**Type:** Enhancement
**Status:** Superseded by #007 (adopt prompt_toolkit)
**Component:** `tapes/importer/interactive.py` -- `edit_companions`
**Depends on:** #005 (arrow key navigation)

---

## Current behavior

The edit companions checklist shows all companion files in a flat list. With
many companions (e.g., a season pack with subtitle files per episode), finding a
specific file requires scrolling through the entire list.

## Proposed behavior

Typing alphanumeric characters enters a fuzzy filter mode:

- A filter input line appears at the bottom (or top) of the checklist.
- The list narrows to entries whose filename matches the typed characters
  (fuzzy, case-insensitive).
- Arrow keys still navigate within the filtered results.
- Space still toggles.
- Backspace removes characters from the filter.
- Escape (or empty filter + Backspace) clears the filter and shows all items.
- Enter confirms the full selection (not just filtered items).

Toggling an item in filtered view affects the underlying selection state, so
items toggled while filtered stay toggled when the filter is cleared.

## Implementation notes

- This depends on arrow key navigation (#005) being implemented first.
- Fuzzy matching can be simple substring or a lightweight algorithm like the one
  used by fzf (sequential character matching with gaps). Start with substring;
  upgrade if needed.
- The filter state is separate from the selection state. Filtering changes what
  is displayed, not what is selected.
- Consider a visual indicator (e.g., `12/47 shown`) to show how many items
  match the current filter.

## Acceptance criteria

- [ ] Typing characters filters the companion list
- [ ] Filtered list updates on each keystroke
- [ ] Arrow navigation works within filtered results
- [ ] Space toggles items in filtered view (persists when filter cleared)
- [ ] Backspace removes filter characters
- [ ] Escape clears filter
- [ ] Enter confirms full selection (all items, not just filtered)
- [ ] Empty filter shows all items
