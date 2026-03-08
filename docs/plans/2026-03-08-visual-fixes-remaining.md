# Remaining Visual Fixes

Status: **completed**

Screenshots of the current state are in `docs/mockups/screenshots/` (gitignored).
Color reference mockups are in `docs/mockups/color-swatches.html`.
Layout mockup showing the aligned-column design is in `docs/mockups/screenshots/column-layout-mockup.html`.

---

## Context

Visual design overhaul is complete. The TUI uses a clean, Claude Code-inspired
layout with horizontal separators, inline views, and a persistent bottom bar.

## Color palette (final)

| Color       | Hex         | Usage                                                    |
|-------------|-------------|----------------------------------------------------------|
| Crail       | `#E07A47`   | `?` placeholders in destinations                         |
| Green       | `#4EBA65`   | Staged tick (✓) in tree view                             |
| Lavender    | `#B1B9F9`   | Accent: active separators, help keys, tab hints          |
| Red         | `#FF7A7A`   | Low confidence, errors                                   |
| Muted       | `#888888`   | Labels, muted text, ignored files, folder names, arrows  |
| Muted Light | `#aaaaaa`   | Folder collapse/expand arrows (▶/▼)                      |
| Inactive    | `#555555`   | Unfocused separator                                      |
| Cursor BG   | `on #373737`| Cursor highlight and range selection                     |

**Important:** We use explicit `#888888` instead of Rich `dim` attribute everywhere.
Rich `dim` halves brightness AND thins font weight, making text look weak.

## All completed fixes

1. **Dim text** — explicit `MUTED = "#888888"` instead of Rich `dim`
2. **Staging display** — green tick (✓ #4EBA65) after arrow, no background color
3. **Folder display** — ▼/▶ arrows, MUTED_LIGHT, 4-space indent
4. **Path compression** — single-child chains merged
5. **Layout overhaul** — horizontal separators, no CSS borders, BottomBar (5 lines)
6. **Inline views** — DetailView, CommitView, HelpView replace modals
7. **Confirm/discard model** — detail edits are pending until `c`; `esc` discards
8. **Keybindings** — `backspace` clear, `f` extract from filename, `enter` expand/edit
9. **Double ctrl+c quit** — replaces `q`, per-view hint display
10. **Scroll indicators** — ↑ more above / ↓ more below (italic, dimmed)
11. **Ignored files** — strikethrough filename, no destination shown
12. **Extension handling** — `full_extension()` for multi-tag subtitles (.forced.en.srt, -forced.en.idx)
13. **Help view** — inline workflow guide with lavender-colored keys
14. **Stats in separator** — embedded in dashes, not flush at edge
15. **Blank line spacing** — above separator in all views

## Files involved

- `tapes/ui/tree_app.py` — CSS, layout switching, inline view management, keybindings
- `tapes/ui/tree_view.py` — Render loop, scroll indicators, staging display
- `tapes/ui/tree_render.py` — Color constants, `render_file_row`, `full_extension`, `render_separator`
- `tapes/ui/tree_model.py` — Path compression (`_compress_single_child_dirs`)
- `tapes/ui/detail_view.py` — Field rendering, confirm/discard, tab cycling
- `tapes/ui/detail_render.py` — Color functions (`diff_style`, `confidence_style`)
- `tapes/ui/help_overlay.py` — Inline HelpView with workflow guide
- `tapes/ui/commit_view.py` — Inline CommitView with file categorization
- `tapes/ui/bottom_bar.py` — Stats, search, operation mode, hints
