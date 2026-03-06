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
- **staged** -- the file is ready to be processed (moved/copied to library).
  Staging is purely a readiness marker -- it does not modify metadata.
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
`enter` on a file (or selection) drills into the detail view.

### 2. Detail view (per file or selection)

Shows the result alongside sources for cherry-picking. Works identically for
a single file or a multi-file selection.

**Single file:**

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
 enter: apply/edit   shift-enter: apply all   r: re-query   esc: back
```

**Multi-file selection:**

```
 3 files selected
 → (various destinations)
╶──────────────────────────────────────────────────────────────────────────────╴
                result       ┃  from filename
 title         Breaking Bad  ┃  BB
 year          (various)     ┃  ·
 season        1             ┃  1
 episode       (various)     ┃  (various)
 ep. title     (various)     ┃  (various)
╶──────────────────────────────────────────────────────────────────────────────╴
 enter: apply/edit   r: re-query (shared)   esc: back
```

`(various)` appears where selected files have differing values.

The `┃` separator visually distinguishes the result (left, what will be used)
from sources (right, reference material).

`·` represents empty/missing values in a source.

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
| `enter` | drill into file/selection detail / toggle folder expand |
| `space` | toggle staged/unstaged (recursive on folders) |
| `v` | toggle range select mode |
| `a` | accept best TMDB match for cursor/selection (apply regardless of confidence) |
| `c` | commit: process all staged files (with confirmation) |
| `r` | refresh: re-run pipeline per file (re-query TMDB using each file's own result values) |
| `x` | ignore file (skip, won't be processed) |

### Detail view

| Key | Action |
|-----|--------|
| `h/j/k/l` or arrows | navigate the field/source grid |
| `enter` on result field | edit that field manually (inline) |
| `enter` on source field | copy that value into result |
| `enter` on source header | apply all non-empty fields from source to result |
| `shift-enter` on source header | apply all fields including clearing empties |
| `r` | re-query TMDB using current (shared) result values |
| `esc` | back to file tree |

## Auto-pipeline behavior

On startup, tapes runs the full pipeline automatically:

1. Scan files, build tree
2. Extract metadata from filenames (guessit) → fills result
3. Query TMDB per file using extracted metadata → populates source columns
4. Auto-accept: if a TMDB match exceeds confidence threshold, apply its
   non-empty fields to result (never overwrite existing values with blanks)
5. Auto-stage files with confident auto-accepted matches

Whether auto-accept is enabled is configurable. Default: auto-accept and
auto-stage confident matches.

## Applying sources to result

When applying a source to the result (whether auto or manual):

- **`enter` on source header / auto-accept / `a` in tree:** fill result fields
  where the source has a value. Skip fields where the source is empty. Never
  overwrite existing result values with nothing. This preserves guessit-only
  fields (codec, resolution) that TMDB doesn't know about.

- **`shift-enter` on source header:** fill ALL result fields from source,
  including clearing fields the source doesn't have. Use when you want to
  fully reset to a specific source.

- **`enter` on individual source field:** copy that single value into the
  corresponding result field. Fine-grained cherry-picking.

## Staging

Staging is purely a readiness marker. It does not modify metadata.

- `space` toggles staged/unstaged. That's it.
- `space` on a folder toggles all children recursively.
- `v` enters range select, `space` stages/unstages the range, `v` clears range.

A file can be staged regardless of whether it has TMDB matches, whether matches
were accepted, or whether metadata was manually edited. Staging means: "process
this file with whatever is currently in its result."

## Two kinds of refresh

**`r` in tree view (per-file refresh):**
Re-runs the pipeline for each file in the cursor/selection individually. Each
file is queried using its own complete result values. Confident matches are
auto-accepted (non-empty fields applied to result, empty fields left alone).
Use after bulk-editing shared fields to fan out individual queries.

**`r` in detail view (shared refresh):**
Queries TMDB once using the shared result values (fields showing `(various)`
are omitted from the query). Returns shared source columns. Use to find
matches based on manually corrected metadata.

## Accept best match

**`a` in tree view:**
Applies the best TMDB match (highest confidence) to result for cursor/selection,
regardless of confidence level. Same application rules as auto-accept: non-empty
source values overwrite result, empty source values don't clear result.

Use when the pipeline returned correct but low-confidence matches and the user
wants to bulk-accept them without drilling into each file.

## Metadata model

The result is just a dict of field values. There is no implicit layering at
runtime. Sources are kept around as reference (the user can always see what
guessit extracted or what TMDB returned) but the result is the single source
of truth.

Every file is a first-class citizen. There is no special "companion" concept
in the TUI. Subtitles, artwork, and other non-video files are just files with
their own result metadata. Guessit extracts similar metadata from similarly-
named files naturally.

Undo tracks changes to the result, so any apply/edit can be reverted.

## Row highlighting

Full row highlight (like lazygit), not a cell crosshair cursor. In the tree
view, the cursor highlights one row. In the detail view, the cursor highlights
one cell in the field/source grid.

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
