# Remaining Visual Fixes

Status: **in progress**

Screenshots of the current state are in `docs/mockups/screenshots/` (gitignored).
Color reference mockups are in `docs/mockups/color-swatches.html`.
Layout mockup showing the aligned-column design is in `docs/mockups/screenshots/column-layout-mockup.html`.

---

## Context

We're iterating on the TUI visual design. The goal is a clean, lazygit-inspired
aesthetic that's easy to scan and navigate. Multiple rounds of fixes have been
applied covering colors, borders, layout, staging display, path compression,
and modal overlays.

## Color palette (decided)

| Color      | Hex         | Usage                                                    |
|------------|-------------|----------------------------------------------------------|
| Crail      | `#E07A47`   | `?` placeholders in destinations                         |
| Green      | `#86E89A`   | Checkmark in commit modal                                |
| Blue       | `#7AB8FF`   | Active border, source name, keybinding hints, modal border |
| Red        | `#FF7A7A`   | Low confidence, errors                                   |
| Purple     | `#C79BFF`   | Reserved                                                 |
| Yellow     | `#FFDF61`   | Reserved                                                 |
| Muted      | `#888888`   | Labels, muted text, ignored files, folder names, arrows, dim destinations |
| Muted Light| `#aaaaaa`   | Folder collapse/expand arrows (▶/▼)                      |
| Inactive   | `#555555`   | Unfocused panel border                                   |
| Cursor BG  | `on #36345a`| Cursor highlight (lazygit-style dark slate)              |
| Staged BG  | `on #1e3320`| Dark mossy green background for staged files             |
| Range BG   | `on #2a2844`| Range selection background                               |
| Modal BG   | `#1a1a2e`   | Modal panel background                                   |

**Important:** We use explicit `#888888` instead of Rich `dim` attribute everywhere.
Rich `dim` halves brightness AND thins font weight, making text look weak.

## Completed fixes

### 1. Dim text looking thin
Replaced all Rich `"dim"` style usage with explicit `MUTED = "#888888"` constant
defined in `tree_render.py` and imported everywhere. Same visual weight as
normal text, just dimmer color.

### 2. Staging display
Removed checkmark/circle/dot markers from tree rows. Staging is now shown via
background color only: dark mossy green (`on #1e3320`) for staged files.
Ignored files get muted text color. Cleaner, less noisy.

### 3. Folder display
- Removed folder emoji icon (terminal rendering issues)
- Using ▼ (expanded) / ▶ (collapsed) Unicode arrows in `MUTED_LIGHT` color
- Folder name in `MUTED` color with trailing `/`
- 4-space indentation per nesting level

### 4. Path compression
Single-child directory chains are merged: `shows/s01/` instead of separate
`shows/` and `s01/` entries. Implemented via `_compress_single_child_dirs()`
in `tree_model.py`, called after `build_tree()`.

### 5. Layout and sizing
- `self.size.width` is already the content area in Textual (no need to subtract
  border width)
- Detail view height set dynamically: `len(fields) + 7`
- Detail view in normal flow (not `dock: bottom`) to avoid footer overlap
- Arrow column recomputes on resize via `on_resize()`

### 6. Modal overlay rewrite
Both `HelpOverlay` and `CommitModal` were rewritten from `Widget` with manual
box-drawing characters to proper Textual container pattern:
- `Middle` > `Center` > `Static` hierarchy
- CSS `border: round #7AB8FF` instead of manual `╭─╮│╰─╯`
- `layer: overlay` + `dock: top` to float over content without scrollbar
- Background widgets dimmed via `.modal-open` class → `opacity: 0.3`
- Help overlay: fixed width 64, auto height, max 90%
- Commit modal: 80% width (min 50, max 100), auto height, max 80%

## Remaining issues

### 1. Textual version upgrade
Currently pinned to `textual>=3,<4` (using 3.7.1). Latest is v8.0.2.
Significant version gap — may have breaking API changes but also likely
improvements to overlay/layer handling that could help with modal rendering.

### 2. Background transparency
The app background may differ from terminal background. Using `textual-ansi`
theme at mount time should help. Needs testing.

### 3. General visual polish
- Verify modal overlay dimming looks right in practice
- Verify detail view sizing works for various field counts
- End-to-end manual testing of all visual states

## Files involved

- `tapes/ui/tree_app.py` — CSS, theme selection, layout switching, modal toggle
- `tapes/ui/tree_view.py` — Arrow column computation, render loop, staging display
- `tapes/ui/tree_render.py` — Color constants, `render_file_row`, `render_folder_row`
- `tapes/ui/tree_model.py` — Path compression (`_compress_single_child_dirs`)
- `tapes/ui/detail_view.py` — Dynamic column widths, field rendering
- `tapes/ui/detail_render.py` — Color functions (`diff_style`, `confidence_style`)
- `tapes/ui/help_overlay.py` — `Middle`/`Center`/`Static` modal with CSS border
- `tapes/ui/commit_modal.py` — `Middle`/`Center`/`Static` modal with CSS border

## Design references

- `docs/plans/2026-03-07-tui-visual-design.md` — authoritative design spec
- `docs/mockups/color-swatches.html` — color reference with all palettes
- `docs/mockups/screenshots/column-layout-mockup.html` — before/after column layout mockup
