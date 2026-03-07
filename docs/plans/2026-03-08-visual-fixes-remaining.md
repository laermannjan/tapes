# Remaining Visual Fixes

Status: **in progress**

Screenshots of the current state are in `docs/mockups/screenshots/` (gitignored).
Color reference mockups are in `docs/mockups/color-swatches.html`.
Layout mockup showing the aligned-column design is in `docs/mockups/screenshots/column-layout-mockup.html`.

---

## Context

We're iterating on the TUI visual design. The goal is a clean, lazygit-inspired
aesthetic that's easy to scan and navigate. We've made several rounds of fixes
(colors, borders, layout) but the user reports there are still issues. The
screenshots were taken **before** the most recent commit (445f1bf) which added
aligned columns, VSCode colors, detail height fix, and ANSI theme — so some of
these may already be improved. The user needs to retest.

## Color palette (decided)

We use the VSCode Claude theme colors:

| Color   | Hex       | Usage                                              |
|---------|-----------|----------------------------------------------------|
| Crail   | `#E07A47` | Unstaged marker, differs diff, medium confidence, `?` placeholders, keybinding hints |
| Green   | `#86E89A` | Staged marker, fills-empty diff, high confidence   |
| Blue    | `#7AB8FF` | Active border, source name, TMDB label             |
| Red     | `#FF7A7A` | Low confidence, errors                             |
| Purple  | `#C79BFF` | Reserved                                           |
| Yellow  | `#FFDF61` | Reserved                                           |
| Dim     | `dim`     | Labels, muted text, ignored files, separators, matching values |
| Inactive| `#555555` | Unfocused panel border                             |
| Cursor  | `#264f78` | Selection/cursor background (`on #264f78`)         |
| Range   | `#1a3a52` | Range selection background (`on #1a3a52`)          |

## Issues to verify / fix

### 1. Background transparency

**Problem:** The app background is visibly different from the terminal background.
The terminal background is warm/dark; the Textual app renders a cooler gray.

**What we tried:** `background: transparent` on Screen (didn't work). Most recent
fix: switch to `textual-ansi` theme at mount time (`on_mount`), which uses
`ansi_default` for backgrounds. This should pass through the terminal background.

**Action:** User needs to retest. If still broken, investigate whether Textual's
`ansi_default` actually works as terminal passthrough, or if we need to set
explicit `background: ansi_default` on Screen/widgets in CSS.

### 2. Detail view sizing when focused

**Problem:** When entering detail view (pressing Enter on a file), the detail
panel expanded to fill all remaining space below the compressed tree, leaving
huge empty space below the actual field rows (see screenshot 2).

**What we tried:** Changed from `height: auto; max-height: 50%` to `height: 14`
(fixed). This should give enough room for header + separator + grid header +
~6 field rows + bottom separator.

**Action:** User needs to retest. If 14 lines is too many or too few for some
templates, consider computing the height dynamically based on the number of
fields: `height = len(fields) + 6` (header lines + separators + grid header).

### 3. Aligned two-column tree layout

**Problem:** Tree rows were a wall of text — filename and destination ran
together with unaligned arrows, making it hard to scan.

**What we implemented:** Arrow column aligns at the widest visible filename +
3 chars padding, capped at 50% of widget width. Computed in
`TreeView._compute_arrow_col()`, stored as `self._arrow_col`, passed to
`render_file_row(..., arrow_col=...)`.

**Action:** User needs to retest. Potential issues:
- Column position may not recompute when the widget resizes (terminal resize).
  May need to recalculate in `render()` or on resize events.
- The 50% cap may be too aggressive or not aggressive enough.
- Folder rows don't participate in alignment (they have no destination).

### 4. General visual polish

**Observations from screenshots (may be outdated):**
- The overall look felt "chaotic" and hard to parse. The aligned columns and
  brighter VSCode colors should help significantly.
- Field labels in the detail view are now `dim` to reduce visual weight.
- The inactive "Detail" border title was barely readable at `$surface-lighten-1`,
  now changed to `#555555`.

**If still not right after retest, consider:**
- Whether the destination rendering (dim dir / normal stem / dim ext) provides
  enough contrast against the background.
- Whether the compact preview (bottom panel in tree-focused mode) adds value
  or just noise.
- Spacing/padding within the tree rows.

## Files involved

- `tapes/ui/tree_app.py` — CSS, theme selection, layout switching
- `tapes/ui/tree_view.py` — Arrow column computation, render loop
- `tapes/ui/tree_render.py` — `render_file_row` with `arrow_col` parameter
- `tapes/ui/detail_view.py` — Dynamic column widths, field rendering
- `tapes/ui/detail_render.py` — Color functions (`diff_style`, `confidence_style`)
- `tapes/ui/help_overlay.py` — Keybinding hint colors
- `tapes/ui/commit_modal.py` — Checkmark and hint colors

## Design references

- `docs/plans/2026-03-07-tui-visual-design.md` — authoritative design spec
- `docs/mockups/color-swatches.html` — color reference with all palettes
- `docs/mockups/screenshots/column-layout-mockup.html` — before/after column layout mockup
