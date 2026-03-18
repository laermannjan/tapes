# Detail View Redesign

Status: **approved**
Date: 2026-03-08

Inspired by Claude Code's TUI design language.

---

## Design Principles

Taken from Claude Code's TUI:

1. **Horizontal lines only.** No vertical separators. Use whitespace (3+ spaces)
   to separate columns.
2. **White/muted hierarchy.** Bold white for primary content, muted for
   supplemental. Color only for actionable signals.
3. **Tabs for navigation.** Active tab is inverted (colored bg, dark fg).
   Inactive tabs are default white. Navigation hint dimmed inline.
4. **Purple focused separator.** The horizontal line above a focused panel
   uses the accent color to indicate focus.
5. **Prose-style footer.** Italicized, muted, `·`-separated keybinding
   hints in natural language.

---

## Detail View (expanded)

### Layout

```
──────────────────────────────────────────────────────  (purple when focused)
Info                  TMDB #1   TMDB #2       ←/→ to cycle

  path/to/file.mkv → Movies/The Matrix (1999)/The Matrix (1999).mkv

  tmdb_id       603            603
  title         The Matrix     The Matrix
  year          1999           1999
  media_type    movie          movie
  season        ?
  episode       ?
──────────────────────────────────────────────────────
```

### Window title

"Info" in purple on the header line (like "Plugins" in Claude Code).

### Left column (editable)

- Field names in muted, values in normal white
- No column header. The fields speak for themselves.
- `j/k` moves cursor through fields (cursor row gets subtle slate bg highlight)
- `Enter` starts inline edit on the cursor field
- `tmdb_id` is always the first field, regardless of template

### Right column (TMDB tabs)

- Tab headers on the header line: "TMDB #1", "TMDB #2", etc.
- Active tab: inverted (accent bg, dark fg). Inactive: default white.
- Confidence shown on active tab: "TMDB #1 85%" (muted if >=80%, ember
  if 50-79%, red if <50%)
- `h/l` cycles active tab
- Content: single column showing active tab's field values
- Diff coloring relative to the left column (editable) values:
  - Muted = source matches current value (or source is None)
  - Green `#86E89A` = current value is empty, source would fill it
  - Ember `#E07A47` = current value differs, source would overwrite
- `Enter` on a field applies the source value to the left column
- `Enter` on header row applies all non-empty source values

### Auto-sized columns

All three column areas (field names, values, source values) auto-size based
on their longest content + padding, similar to how the tree view computes
`arrow_col` from the longest filename.

### File path

Full relative path shown (not just filename). Same styling as tree view:
`path/to/file.mkv → destination` on one line.

---

## Detail View (compact / unfocused)

```
  path/to/file.mkv → Movies/The Matrix (1999)/The Matrix (1999).mkv
  tmdb: 603  85%
```

Line 1: filename and destination (same styling as tree view row).
Line 2: `tmdb_id` value + confidence. Confidence only shown when `tmdb_id`
is set in the result. If no `tmdb_id`, just show `tmdb: ?`.

---

## Panel Focus

### Focused panel indicator

Replace CSS `border: round` with a simpler approach:
- Focused panel: purple horizontal line (`─`) as top border
- Unfocused panel: muted horizontal line

Or keep the round border but change its color (purple when focused,
muted when unfocused). Either works. The current `#7AB8FF` blue border
changes to purple to match Claude Code's accent.

### Tree view dimming

When the detail view is focused, the tree view content should appear at
reduced contrast. Add a class that switches tree text to a more muted
color (e.g., `#555555` or `#666666`).

---

## Footer (StatusFooter)

Prose-style, italicized, muted, `·`-separated:

- Tree mode: *Space to stage · Enter for details · a to accept · c to commit · ? for help*
- Detail mode: *Enter to apply · ⇧Enter to apply all · ←/→ to cycle sources · Esc to go back · ? for help*
- Edit mode: *Enter to confirm · Esc to cancel*

---

## Commit Modal

```
  Process 5 files?

  Operation: [copy]             ←/→ to change

  y confirm · n cancel
```

- No file list (staging already handles that)
- Operation selector: cycles through copy, move, link, hardlink
- Default: configured operation from `LibraryConfig.operation`
- Returns both confirmation boolean and selected operation string
- Background: same as main screen (no explicit bg color)

---

## Color Palette Updates

| Element              | Old                  | New                        |
|----------------------|----------------------|----------------------------|
| Focused border/line  | `#7AB8FF` (blue)     | Purple accent (TBD exact)  |
| TMDB label in header | `#7AB8FF` (blue)     | Default white               |
| Active tab           | n/a                  | Inverted (accent bg, dark fg) |
| Inactive tab         | n/a                  | Default white               |
| Confidence >=80%     | `#86E89A` (green)    | Muted `#888888`            |
| Confidence 50-79%    | `#E07A47` (ember)    | `#E07A47` (ember, unchanged) |
| Confidence <50%      | `#FF7A7A` (red)      | `#FF7A7A` (red, unchanged) |
| Missing values       | `·` (centered dot)   | `?`                        |
| Modal background     | `#1a1a2e`            | Transparent / terminal bg  |

---

## Behavioral Changes

- **Editing clears tmdb_id.** When a user manually edits any field, `tmdb_id`
  is removed from the result. The TMDB identification no longer applies.
- **Missing values always `?`.** Both in the detail grid and in destinations.
  No more centered dot `·`.

---

## Files Affected

- `tapes/ui/detail_view.py` -- major rewrite (tab bar, single-column content, auto-sizing)
- `tapes/ui/detail_render.py` -- update display_val, compact preview, confidence_style
- `tapes/ui/tree_app.py` -- CSS changes, footer, focus management
- `tapes/ui/tree_view.py` -- dimming when unfocused
- `tapes/ui/commit_modal.py` -- redesign (operation selector, no file list)
- `tapes/ui/help_overlay.py` -- background color fix
