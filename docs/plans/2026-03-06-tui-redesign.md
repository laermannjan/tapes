# TUI Redesign: lazygit-inspired interaction model

## Overview

Redesign the grid TUI from a command-driven spreadsheet into a lazygit-inspired
file tree with drill-in detail view. Core concepts: staging, source-based
metadata curation, minimal keys with context-dependent behavior.

## Mental model

The user has files. Each file needs metadata to compute a destination path.
Metadata comes from **sources**: filename extraction (guessit), TMDB matches,
or manual input. The user curates the **result** by cherry-picking values from
sources. Once the result looks right, they **stage** the file. When ready, they
**commit** (process) all staged files.

```
nothing → guessit → TMDB → result → destination
          (auto)    (auto)  (curated)  (computed)
```

## Terminology

- **result** -- the final metadata for a file, used to compute the destination
  path. A merge of values from various sources and manual edits.
- **source** -- something that provides metadata values. Built-in sources:
  `from filename` (guessit), `TMDB #1`, `TMDB #2`, etc.
- **staged** -- the file's result is accepted, ready to be processed (moved/
  copied to library).
- **unstaged** -- the file needs attention (unidentified, low confidence, or
  user hasn't reviewed yet).
- **ignored** -- not a media file, or user explicitly skipped it.
- **commit/process** -- execute the file operations for all staged files.

## Two views

### 1. File tree (main view)

Shows the scanned directory as a tree with destinations:

```
~/downloads/
├── ✓ Breaking.Bad.S01E01.720p.mkv   → TV/Breaking Bad (2008)/S01/…E01 - Pilot.mkv
├── ✓ Breaking.Bad.S01E01.en.srt     → TV/Breaking Bad (2008)/S01/…E01 - Pilot.en.srt
├── ✓ Breaking.Bad.S01E02.720p.mkv   → TV/Breaking Bad (2008)/S01/…E02 - Cat's in the Bag.mkv
├── ○ movie_final_cut.mkv            → ???
├──   thumbs.db
└── subfolder/
    ├── ✓ Inception.2010.1080p.mkv   → Movies/Inception (2010)/Inception (2010).mkv
    └── ✓ Inception.2010.en.srt      → Movies/Inception (2010)/Inception (2010).en.srt
```

Markers: `✓` staged, `○` unstaged (needs attention), no marker = ignored/dimmed.

Directories are collapsible. `enter` on a directory toggles expand/collapse.
`enter` on a file drills into the detail view.

Staging: `space` toggles staged/unstaged on cursor file. `space` on a directory
toggles all children recursively. `v` enters range select mode (contiguous
block), `space` stages/unstages the range, `v` again clears the range.

### 2. Detail view (per file)

Shows the file's result alongside sources for cherry-picking:

```
 Breaking.Bad.S01E01.720p.BluRay.x264.mkv
 → TV/Breaking Bad (2008)/Season 01/Breaking Bad - S01E01 - Pilot.mkv
╶──────────────────────────────────────────────────────────────────────────────╴
                result       ┃  from filename    TMDB #1 (95%)   TMDB #2 (71%)
 title         Breaking Bad  ┃  Breaking Bad     Breaking Bad    Breaking Bad UK
 year          2008          ┃  ·                2008            2019
 season        1             ┃  1                1               1
 episode       1             ┃  1                1               1
 ep. title     Pilot         ┃  ·                Pilot           Episode 1
 codec         x264          ┃  x264             ·               ·
 source        BluRay        ┃  BluRay           ·               ·
╶──────────────────────────────────────────────────────────────────────────────╴
 enter: apply/edit   shift-enter: apply all   r: refresh   esc: back
```

The `┃` separator visually distinguishes the result (left, what will be used)
from sources (right, reference material).

`·` represents empty/missing values.

The destination line at the top updates live as the result changes.

Fields shown are determined by the configured template -- only fields the
template actually needs are displayed.

## Keymap

### Global

| Key | Action |
|-----|--------|
| `q` | quit (confirm if staged files exist) |
| `u` | undo last action |
| `/` | fuzzy search/filter file tree |
| `esc` | cancel/back/clear filter |

### File tree

| Key | Action |
|-----|--------|
| `j/k` or `↑/↓` | navigate rows |
| `enter` | drill into file detail / toggle folder expand |
| `space` | toggle staged/unstaged (recursive on folders) |
| `v` | toggle range select mode |
| `c` | commit (process all staged files, with confirmation) |
| `r` | refresh: re-run pipeline (guessit + TMDB) on cursor/selection |
| `x` | ignore file (skip, won't be processed) |

### Detail view

| Key | Action |
|-----|--------|
| `h/j/k/l` or arrows | navigate the field/source grid |
| `enter` on result field | edit that field manually (inline) |
| `enter` on source field | copy that value into result |
| `enter` on source header | apply all non-empty fields from source to result |
| `shift-enter` on source header | apply all fields including clearing empties |
| `r` | re-query TMDB using current result values |
| `esc` | back to file tree |

## Auto-pipeline behavior

On startup, tapes runs the full pipeline automatically:

1. Scan files, build tree
2. Extract metadata from filenames (guessit) → fills result
3. Query TMDB using extracted metadata → adds source columns
4. Auto-accept: if a TMDB match exceeds confidence threshold, overlay its
   non-empty fields onto result (never overwrite filled values with blanks)
5. Auto-stage files with confident matches

Whether auto-accept replaces result values or leaves them for manual review
is configurable. Default: auto-accept confident matches.

## Applying sources to result

When applying a source to the result (whether auto or manual):

- **`enter` on source header / auto-accept:** fill result fields where the
  source has a value. Skip fields where the source is empty. Never overwrite
  existing result values with nothing. This preserves guessit-only fields
  (codec, resolution) that TMDB doesn't know about.

- **`shift-enter` on source header:** fill ALL result fields from source,
  including clearing fields the source doesn't have. Use when you want to
  fully reset to a specific source.

- **`enter` on individual source field:** copy that single value into the
  corresponding result field. Fine-grained cherry-picking.

## Metadata layering

The result is built up from sources but is its own thing. There's no implicit
layering at runtime -- the result is just a dict of field values. Sources are
kept around for reference (the user can always see what guessit extracted or
what TMDB returned) but the result is the single source of truth.

Undo tracks changes to the result, so any apply/edit can be reverted.

## Row highlighting

Full row highlight (like lazygit), not a cell crosshair cursor. In the tree
view, the cursor highlights one row. In the detail view, the cursor highlights
one cell in the field/source grid.

## Companion files

Companion files (subtitles, artwork) inherit metadata from their video file.
They appear in the tree under the same directory. Their destinations are
computed from the same result plus their own extension/language suffix.

Staging a video file auto-stages its companions. The detail view for a
companion shows the inherited result (read-only) with a note about which
video file it's linked to.

## Processing

`c` in tree view opens a confirmation showing:
- Number of staged files
- Operation (copy/move/link from config)
- Dry-run preview

`enter` to confirm, `esc` to cancel.

## Fuzzy search

`/` enters search mode. A text input appears, typing filters the tree to
matching filenames. `enter` jumps to the match. `esc` clears the filter
and returns to full tree view.
