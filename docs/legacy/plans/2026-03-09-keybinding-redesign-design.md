# Keybinding Redesign

## Goal

Streamline the keyboard workflow so common actions flow naturally and
rare actions use less prominent keys. Reduce the number of random letter
keymaps the user must remember.

## Design principles

- **tab forward, esc back, enter confirm.** Navigation through workflow
  stages uses these three universal keys.
- **space = stage.** Consistent everywhere.
- **Staging gate.** A file can only be staged when its template fields
  are complete. No validation at commit time.
- **Detail confirm = stage.** Accepting metadata in detail view
  auto-stages the file (if template is complete).
- **Column focus in detail view.** The user chooses which column (result
  or current match) to accept. A light purple background on field values
  makes the focused column obvious. `enter` applies the focused column's
  values and returns to tree.

## Staging gate

A file is **ready to stage** when `can_fill_template` returns true for
its current result dict (all required template fields are non-None).

- `space` / `enter` on a file in tree view only stages if the file is
  ready. Otherwise it does nothing (or notifies the user).
- Visual indicator in tree view: `☐` for ready-to-stage (template
  complete, not staged), `✓` for staged, nothing for incomplete.
- Commit view no longer validates metadata completeness -- if a file is
  staged, it is guaranteed processable.

## Keybindings

### Tree view

| Key | Action |
|-----|--------|
| j / k / up / down | move cursor |
| enter | file: stage/unstage (same as space). folder: select all files recursively and open detail view |
| space | stage / unstage (blocked if template incomplete) |
| h / left | collapse folder (or move to parent) |
| l / right | expand folder |
| x | ignore file |
| v | visual range select, then enter to open detail for selection |
| / | search/filter |
| tab | open commit preview |
| shift+tab | cycle operation (copy/move/link/hardlink) |
| r | re-query TMDB for file at cursor |
| - / = | collapse all / expand all |
| \` | toggle flat/tree mode |
| ? | help |
| ctrl+c ctrl+c | quit |

**Removed:** `c` (replaced by `tab` for commit, detail confirm is now
`enter`).

### Detail view

| Key | Action |
|-----|--------|
| j / k / up / down | move cursor through fields |
| tab | cycle forward through TMDB matches (focuses match column) |
| shift+tab | toggle focus between result column and current match |
| enter | accept focused column's values and return to tree (auto-stages if template complete) |
| esc | discard all changes and return to tree |
| e | edit current field inline (enter confirms edit, esc cancels) |
| backspace | clear current field |
| ctrl+r | reset current field to filename-extracted value |
| r | refresh TMDB matches |

**Removed:** `c` (confirm -- replaced by `enter`), `ctrl+a` (accept all
from match -- replaced by focusing match column + `enter`), `f` (extract
from filename -- replaced by `ctrl+r`), left/right arrows for cycling
matches (replaced by `tab`/`shift+tab`).

**Column focus:** The detail view tracks which column is "focused for
acceptance": either the result column or the currently visible match
column. Field values in the focused column get a light purple background
(`#3B3154` or similar). `tab` cycles matches and sets focus to the match
column. `shift+tab` toggles between result and match. `enter` applies
fields from the focused column (if match: copies non-None fields to
result, preserving per-file fields the match doesn't have) and returns
to tree view.

### Commit view

| Key | Action |
|-----|--------|
| enter | confirm and start processing |
| esc | cancel (back to tree, or cancel in-progress operation) |
| shift+tab | cycle operation |
| ? | help |
| ctrl+c ctrl+c | quit |

### Inline editing (within detail view)

When `e` is pressed to edit a field:

| Key | Action |
|-----|--------|
| any printable | append to edit buffer |
| backspace | delete last character |
| enter | confirm edit (auto-triggers TMDB refresh if value changed) |
| esc | cancel edit |

## Visual changes

1. **Tree view staging indicator:** `☐` (unfilled square) for
   ready-to-stage files, `✓` (green check) for staged files, no
   indicator for files with incomplete metadata.

2. **Detail view column focus:** Light purple background (`#3B3154`)
   on all field values in the focused column (result or match). The
   existing tab bar highlighting is unchanged.

## What stays the same

- Overall layout (tree, inline detail/commit/help views, bottom bar)
- Detail view grid structure (single match column visible at a time)
- Tab bar appearance and positioning
- TMDB auto-refresh after field edits
- Confirm/discard model (snapshot on open, restore on discard)
- Double ctrl+c quit with 1-second window
- Search mode (/ to enter, enter to confirm, esc to cancel)
