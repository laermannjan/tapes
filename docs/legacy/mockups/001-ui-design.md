# 001 -- UI Design Vision

Supersedes: nothing (first iteration)
Date: 2026-03-06

---

## Overview

Tapes is an interactive CLI for organizing messy media file collections. The UI
is a spreadsheet-like grid rendered in the terminal. Design language is inspired
by Claude Code: minimal chrome, monochrome primary palette, sparse color for
meaning.

## Core loop

1. User runs `tapes import /path`
2. Tapes scans recursively for video files
3. For each video, companion files are discovered (stem-prefix matching)
4. Metadata is extracted via guessit (title, year, season, episode, etc.)
5. Results are displayed as an interactive, navigable, editable grid
6. User can query TMDB to refine metadata
7. User enters process mode to review and execute file operations

## The grid

Every file gets its own row -- videos and companions alike. Companions are
dimmed but structurally identical to video rows (same columns, same
editability). This allows users to fix misattributed companions by editing
their metadata and reorganizing.

### Columns

```
[status] filepath                          | title | year | season | episode | episode_title
```

- **Status badge** (left margin, in dimmed brackets): `[..]` guessit raw,
  `[**]` auto-accepted TMDB, `[??]` uncertain TMDB match, `[!!]` user-edited,
  `[--]` frozen
- **Filepath** (left-aligned): relative to the scan root. For videos, the
  filename portion is white; the directory prefix is dim. For companions,
  the entire path is dim.
- **Metadata fields** (right side, column-organized): each field gets its own
  column with consistent alignment.
  - **Default visible columns:** `title`, `year`, `season`, `episode`,
    `episode_title`, `tmdb_id`
  - **Additional columns** (hidden by default, user-configurable):
    `codec`, `container`, `hdr`, `resolution`, `media_source`, `audio`, etc.
    These are never part of TMDB queries but may be used in path templates.
    The full list of available fields is predetermined but extensible.

### Grouping and sort order

Rows are sorted by: title > year > season > episode.

Visual groups are formed by:
- Movies sharing the same title + year
- Episodes sharing the same title + year + season

Groups are separated by empty lines or subtle horizontal rules. Some or all
sort fields may be unknown.

### Companion files

Companions are full grid rows with the same metadata columns. They are dimmed
to signal secondary importance. Because companions share the video's filename
stem, guessit extracts the same metadata -- so they appear grouped correctly by
default. If a companion is misattributed, the user edits its metadata fields
and presses `r` to reorganize, which moves it to the correct group.

## Navigation and interaction

### Modes

1. **Normal mode** -- navigate, view
2. **Select mode** -- multi-cell/row selection
3. **Edit mode** -- inline field editing
4. **Query mode** -- TMDB lookup results displayed inline
5. **Process mode** -- destination paths replace metadata columns

### Cursor (crosshair)

- Crosshair cursor: the current row gets a subtle row highlight, the current
  column gets a subtle column highlight, and the intersection cell (active
  cell) is the brightest. This creates a crosshair shape.
- The column highlight covers **all** rows including empty separator rows,
  forming a continuous vertical stripe (like a spreadsheet column).
- Arrow keys: left/right between fields, up/down between rows
- Cursor moves across all rows (videos and companions)

### Select (v)

- Selection is **column-locked**: only vertical, never multiple columns.
  Left/right navigation is blocked while selection is active.
- Selection highlighting is **mossy green** (`#3a5a3a` for selected cells,
  `#1a241a` for selected rows, `#4a6a4a` for selected+cursor). Dim text
  gets boosted via `_SEL_TEXT` lookup for readability on green backgrounds.
- `v` activates **selecting mode**: the current cell is selected, and
  subsequent up/down arrow presses add cells to the selection.
- `v` again **pauses** selecting mode: selection stays visible and active,
  but cursor moves freely without adding cells.
- `v` again **resumes** selecting from the current position.
- `V` (shift-v) selects all file rows in the cursor's group. If the group
  is already fully selected, it deselects the group instead (toggle).
- Non-adjacent selection: pause selecting, navigate, resume selecting
  elsewhere, or use `V` on different groups.
- `esc` clears the entire selection.
- Actions (`e`, `q`, `f`) that work on selections default to the cursor
  cell when no selection is active.

### Edit (e) -- inline

- No selection: edits the field under the cursor
- With selection: edits all selected fields simultaneously
- Live inline editing: the cell shows the edit buffer with underline styling.
  No separate input widget -- typing happens directly in the cell.
- `esc` to cancel (no changes applied), `enter` to confirm
- On confirm, only the **changed fields** turn purple (`#a78bfa`). Unchanged
  fields retain their original color. The row's status badge becomes `[!!]`.
- Int fields (`year`, `season`, `episode`) are validated on confirm; invalid
  input cancels silently.
- Selection persists after edit. Cursor jumps to the topmost selected row.
- Frozen fields cannot be edited (edit is blocked).

### Undo (u)

- Reverts the last edit or query action.
- Restores full row state (overrides, status, edited fields).
- Undo is cleared when selection is cleared via `esc`.

### Edit all fields (Shift+E) -- modal

Opens a modal overlay for editing all available metadata fields at once.

- **Title bar**: filename of the current row (or "N files" if multi-selection)
- **Body**: form listing all available metadata fields as key-value pairs
  - Key: field name (left-aligned, dim)
  - Value: prepopulated with current value, editable
  - When multiple rows are selected and values differ: show dimmed `(various)`
  - Includes both default and additional fields (codec, hdr, etc.)
- **Navigation**: `tab`/`shift-tab` between fields
- **Confirm**: `enter` to accept and overwrite all changed fields
- **Cancel**: `esc` to discard

This modal is the primary way to view and edit additional metadata fields that
are not shown as columns in the grid. It also serves as a quick way to edit
multiple fields on a row without navigating between columns.

### Reorganize (r)

- Re-sorts and re-groups all rows based on current metadata values
- Cursor tracks the file it was on (follows the row, not the position)
- No-op if nothing changed

### Freeze (f / F)

- `f` toggles freeze on the current field for the cursor cell or selected cells.
  Pressing again unfreezes.
- `F` (shift-f) toggles freeze on ALL fields for the cursor row or selected rows.
- Frozen fields are skipped by query and cannot be edited.
- Frozen fields are rendered in cyan (`#66cccc`). When all fields are frozen,
  status badge becomes `[--]`.
- Selection persists after freeze. Cursor jumps to topmost selected row.

### Query (q / Q)

- No selection: queries the cursor row
- With selection: queries only selected rows
- `Q` (shift-q) queries ALL file rows regardless of selection
- Before querying, rows with identical query parameters are grouped so each
  unique query runs only once. Companions sharing a video's metadata get the
  same result.
- Re-querying rejects/clears any pending uncertain matches in the scope

#### Match results

- **Confident match** (similarity above threshold): fields auto-replaced,
  status becomes `**`. Visual indication that data came from TMDB.
- **Uncertain match** (below threshold): original row stays, a sub-row appears
  below showing the match candidate. The `(match)` label is yellow:
  ```
  [??] brbe/BreakBad.s01e01.mkv          episode | BreakBad   |         | 1 | 1 |
   ⎿ (match)                                     | Breaking Bad | 2008  | 1 | 1 | Pilot
  ```
- **No match**: `⎿ (no match)` sub-row in red

#### Accept/reject uncertain matches

- Cursor on match row: `enter` to accept, `backspace`/`delete` to reject
- Accepting updates all rows in the query group (including companions)
- Matches apply at the query-group level (same logical entity)

### Process mode

Entering process mode swaps the right side of the grid:

**Normal mode:**
```
[..] filepath                    | title    | year | season | episode | episode_title
```

**Process mode:**
```
copy filepath                    | Library/Title (Year)/Season 01/Title - S01E01 - Episode.mkv
```

- Status badge is replaced by the operation mode: `copy`, `move`, `link`, `hardlink`
- Operation mode is a global config setting, displayed per-row
- Destination path is generated from a configurable template populated with
  current metadata values
- Destination is relative to a preconfigured library root

#### Entering process mode with pending uncertain matches

If `??` rows exist, the user is prompted:
- Accept all uncertain matches and enter process mode
- Reject all uncertain matches and enter process mode
- Cancel and stay in normal mode

#### In process mode

- `enter` to accept and execute all file operations
- `esc` to go back to normal mode
- No editing, no navigation between fields -- it is a confirmation screen

## Color language

Minimal palette. Monochrome base (grey/white/black). Color is used sparingly
and consistently to convey meaning.

| Color      | Hex       | Meaning                                          |
|------------|-----------|--------------------------------------------------|
| **White**  | `#dddddd` | Primary text (video filenames, important values)  |
| **Dim grey** | `#555555` | Secondary (companions, unfocused rows, chrome)  |
| **Yellow** | `#ccaa33` | Uncertain, needs attention (`[??]` matches)      |
| **Green**  | `#55aa99` | Auto-accepted TMDB (`[**]` badge and field text) |
| **Purple** | `#a78bfa` | User-edited (`[!!]` manually changed fields)     |
| **Red**    |           | Problem, no match, error states                  |
| **Cyan**   | `#66cccc` | Frozen fields and `[--]` badge                   |
| **Mossy green** | `#3a5a3a` | Selected cell background                    |

### Status badge colors

Badges are rendered in dimmed brackets: `[badge]`. Brackets are `#333333`.

| Badge  | Meaning             | Color        |
|--------|---------------------|--------------|
| `[..]` | Guessit raw         | `#555555`    |
| `[**]` | Auto-accepted TMDB  | `#55aa99`    |
| `[??]` | Uncertain match     | `#ccaa33`    |
| `[!!]` | User-edited         | `#a78bfa`    |
| `[--]` | Frozen              | `#66cccc`    |

## Keybindings summary

| Key          | Context       | Action                                    |
|--------------|---------------|-------------------------------------------|
| Arrow keys   | Normal        | Navigate cursor between fields and rows   |
| Arrow keys   | Selecting     | Navigate and add cells to selection       |
| `v`          | Normal        | Start selecting mode (adds current cell)  |
| `v`          | Selecting     | Pause selecting (selection stays, cursor free) |
| `v`          | Paused        | Resume selecting from current position    |
| `V`          | Any           | Toggle-select all rows in cursor's group  |
| `e`          | Normal/Select | Edit field(s) inline                      |
| `u`          | Normal/Select | Undo last edit or query                   |
| `Shift+E`    | Normal/Select | Open metadata editor modal (all fields)   |
| `f`          | Normal/Select | Toggle freeze on field(s)                 |
| `F`          | Normal/Select | Toggle freeze on entire row(s)            |
| `q`          | Normal/Select | Query TMDB (cursor row or selection)      |
| `Q`          | Any           | Query TMDB (all rows)                     |
| `r`          | Normal        | Reorganize (re-sort, re-group)            |
| `enter`      | Edit          | Confirm edit                              |
| `enter`      | Match row     | Accept uncertain match                    |
| `backspace`  | Match row     | Reject uncertain match                    |
| `p`          | Normal        | Enter process mode                        |
| `esc`        | Edit          | Cancel edit (selection preserved)         |
| `esc`        | Select        | Clear selection and undo history          |

## Visual reference

See `docs/mockups/002-mockup.html` for an interactive HTML storyboard showing
all UI states: normal mode, selection, query results, match acceptance, inline
edit, modal edit, process mode, and post-import output.

## Implementation notes

- This is a terminal UI, not a web app. Mockups are HTML for fast iteration.
- The existing Textual-based TUI (`tapes/ui/app.py`) and the previous mockup
  (`docs/mockups/tui-mockup.html`) represent an earlier design direction
  (group-level accordion with accept/skip). This new design supersedes that.
- The grid approach is closer to a spreadsheet or vim-style navigation.
- Technology choice (Textual, raw ANSI, blessed, etc.) is TBD.

## Resolved from previous design

- **Split/merge**: no longer explicit operations. Grouping is implicit via
  matching metadata. Edit fields + reorganize (`r`) to move files between groups.
- **Inline search (`/`)**: no longer a separate action. Query (`q`) on a single
  selected row achieves the same thing. Select the row with `v`, press `q`.

## Resolved from implementation

- **Column header row**: yes, with dimmed labels and a horizontal separator
- **Column widths**: fixed (`status:5, filepath:52, title:16, year:6,
  season:4, episode:4, episode_title:32`). Truncation uses ellipsis char.
- **Cursor foreground**: never changes text color, only background

## Open questions for future iterations

- Truncation strategy for very narrow terminals
- How many metadata columns to show by default vs hiding behind a scroll
- Scrolling behavior for large file lists
