# TUI Visual Design

Status: **draft** (under active discussion)

Mockups: `docs/mockups/tui-visual-design.html`
Walkthrough: `docs/plans/2026-03-07-tui-walkthrough-draft.md`

---

## Layout

Stacked panels. Tree on top, detail on bottom. Both full width.

- **Tree focused (browsing):** Tree fills most of the terminal. Detail panel
  shows a compact 2-line preview at the bottom (filename, destination, key
  fields, TMDB confidence).
- **Detail focused (editing):** Detail panel expands upward. Tree compresses
  to ~5 rows but stays visible for context.

Panels use box-drawing border characters (`┌─┐│└─┘`). The active panel has a
cyan border. The inactive panel has a dim border. Panel titles are embedded in
the top border (`┌─ Files ───┐`). Status info is embedded in the bottom border
of the tree panel (`├── 2 staged / 7 total ──┤`).

---

## Tree View

Full-width file list with destinations.

```
│ ✓ Breaking.Bad.S01E01.720p.BluRay.x264.mkv   → Breaking Bad (2008)/S01E01.mkv   │
│ ○ Inception.2010.1080p.mkv                    → Inception (2010)/Inception.mkv    │
│ ▼ extras/                                                                         │
│   ○ behind_the_scenes.mkv                     → ?                                 │
│   · featurette.mkv                                                                │
```

- `✓` (green) = staged, ready to process
- `○` (yellow) = unstaged, needs review
- `·` (dim) = ignored, entire row dimmed
- `▼`/`▶` = folder expanded/collapsed
- `→` arrow in dim
- Destination path uses template variable emphasis (see below)
- Cursor = full-row highlight (reverse/selection background)
- 2-space indent per depth level

---

## Detail View

One source at a time. Result on the left, one TMDB source on the right.

```
│ Inception.2010.1080p.BluRay.x264-GROUP.mkv                                │
│ → Inception (2010)/Inception (2010).mkv                                   │
│ ────────────────────────────────────────────────────────────────────────── │
│              result                    TMDB #1 (92%)              [1/2]   │
│ ────────────────────────────────────────────────────────────────────────── │
│  title       Inception                 Inception                          │
│  year        2010                      2010                               │
│  media_type  movie                     movie                              │
│  codec       x264                      ·                                  │
│  source      BluRay                    ·                                  │
```

### Diff highlighting

Source values are colored relative to the result:

- **Dim** = matches result (nothing to do)
- **Yellow** = differs from result (would change if applied)
- **Green** = fills an empty slot in result (new value)
- **Dim `·`** = missing in source

Result values are always bold/bright.

### Navigation

`h/l` cycles through TMDB sources only (`[1/N] → [2/N] → ...`).
`j/k` moves between field rows. Navigation is 1D (rows only), not 2D.

### Filename extraction

The filename (guessit) extraction is **not** a source. It is the base layer.
The result starts with filename-extracted values. TMDB values are layered on
top via auto-accept. Only TMDB results appear as sources to cycle through.

### Multi-file selection

When multiple files are selected, the detail view operates on the selection
as a group. Same view, same interactions — every operation applies to all
selected files.

- **Shared fields** (same value across all files): displayed normally.
  Editing, clearing, or applying from a source affects all files.
- **Differing fields**: displayed as `(N values)`. Still editable with `e`
  — the typed value overwrites that field on all selected files. `d` clears
  for all. `D` resets each file to its own filename-extracted value.
- **Header**: shows `N files selected` instead of a single filename.
- **TMDB query**: runs using the shared field values (title, year,
  media_type). Sources are show/movie-level matches.
- **Applying a source**: sets identity fields (title, year, tmdb_id) on all
  files. For TV, triggers per-file episode matching in the background — each
  file's existing season/episode numbers are matched against the show's
  episode data from TMDB.

This handles the key multi-file use cases: misclassified movie + companions,
TV show with filename typo, wrong media_type, multi-season re-identification.

---

## Interactions

### Tree view

| Key       | Action                    |
|-----------|---------------------------|
| `j/k`     | Move cursor               |
| `enter`   | Open detail / toggle folder |
| `space`   | Toggle staged             |
| `a`       | Accept best TMDB source   |
| `x`       | Toggle ignored            |
| `v`       | Range select              |
| `c`       | Commit staged files       |
| `u`       | Undo                      |
| `/`       | Search / filter           |
| `` ` ``   | Toggle flat/tree mode     |
| `-`/`=`   | Collapse/expand all       |
| `r`       | Refresh TMDB query        |
| `q`       | Quit                      |
| `?`       | Help overlay              |

### Detail view

| Key       | Action                          |
|-----------|---------------------------------|
| `j/k`     | Move between fields             |
| `h/l`     | Previous/next TMDB source       |
| `enter`   | Apply field from current source |
| `⇧enter`  | Apply all fields from source    |
| `e`       | Edit result field inline        |
| `d`       | Clear result field (set to ·)   |
| `D`       | Reset field to filename value   |
| `r`       | Re-query TMDB                   |
| `u`       | Undo                            |
| `esc`     | Back to tree                    |
| `?`       | Help overlay                    |

### Inline editing

Press `e` on a field row. The result value becomes an editable text input
(cyan text, block cursor). The source value stays visible as reference.
`enter` confirms, `esc` cancels. The destination path updates after confirm.

---

## Footer

Single row at the bottom of the terminal. Shows only the most relevant
shortcuts for the currently focused panel. No duplicate rows.

Tree focused:
```
 space stage  enter detail  a accept  c commit  ? help
```

Detail focused:
```
 enter apply  ⇧enter apply all  h/l sources  esc back  ? help
```

Edit mode:
```
 enter confirm  esc cancel
```

---

## Help Overlay

Press `?` from any view. A centered bordered modal lists all shortcuts grouped
by view (Files / Detail), plus brief explanations of concepts:

- `✓` staged = file will be processed on commit
- `○` unstaged = needs review, check destination
- `·` ignored = skipped entirely
- Sources provide metadata from TMDB. Apply values to the result to build
  the destination path.

Close with `?` or `esc`.

---

## Modals

Only for confirmations. The commit modal lists staged files with destinations:

```
┌─ Commit ──────────────────────────────────┐
│                                           │
│  Copy 2 files to library?                 │
│                                           │
│  ✓ Breaking.Bad.S01E01.720p.BluRay.mkv    │
│    → Breaking Bad (2008)/S01/S01E01.mkv   │
│  ✓ Breaking.Bad.S01E02.720p.BluRay.mkv    │
│    → Breaking Bad (2008)/S01/S01E02.mkv   │
│                                           │
│  y confirm    n cancel                    │
│                                           │
└───────────────────────────────────────────┘
```

Background panels are dimmed while the modal is open.

---

## Color System

Semantic colors only. No decorative color.

| Element                    | Color        |
|----------------------------|--------------|
| Staged marker `✓`          | Green        |
| Unstaged marker `○`        | Yellow       |
| Ignored files              | Dim (gray)   |
| Active panel border        | Cyan         |
| Inactive panel border      | Dim          |
| Destination arrow `→`      | Dim          |
| Dest. directory path       | Dim          |
| Dest. filename stem        | Normal (fg)  |
| Dest. extension            | Dim          |
| Dest. unresolved           | Yellow `?`   |
| Filename (detail header)   | Bold white   |
| Result column values       | Bold white   |
| Source — matches result     | Dim          |
| Source — differs from result| Yellow       |
| Source — fills empty slot   | Green        |
| Missing value `·`          | Dim          |
| TMDB source labels         | Blue         |
| Confidence ≥80%            | Green        |
| Confidence 50-79%          | Yellow       |
| Confidence <50%            | Red          |
| Cursor row                 | Selection bg |
| Inline edit text           | Cyan         |
| Keybinding hints           | Cyan         |

---

## Destination Path Rendering

Destinations are built from templates like
`TV/{title} ({year})/Season {season}/{title} - S{season}E{episode} - {ep_title}.{ext}`.

The directory path and extension are dim. The filename stem is normal text color.
The filename is where per-file differences live (episode numbers, titles). The
folder hierarchy repeats across files and fades into the background.

- **Directory path** (everything before the last `/`): dim.
- **Filename stem** (after the last `/`, before the extension): normal (fg).
- **Extension**: dim.
- **Arrow** `→`: dim.
- **Unresolved destination**: `?` in yellow.

```
→ TV/Breaking Bad (2008)/Season 1/Breaking Bad - S01E01 - Pilot.mkv
  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^                                  ← dim (directory)
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^    ← normal (filename stem)
                                                                  ^^^^← dim (extension)
```

---

## Compact Detail Preview

When the tree is focused, the detail panel shows a 2-line compact preview
for the hovered file:

```
│ Inception.2010.1080p.BluRay.x264-GROUP.mkv  → Inception (2010)/Inception.mkv   │
│ title: Inception  year: 2010  type: movie  S: ·  E: ·              TMDB 92%    │
```

Key fields on one line. TMDB confidence on the right. Enough to verify at a
glance without entering detail mode.

For folders, the preview shows a summary:

```
│ extras/                                                                        │
│ 2 files · 1 unstaged · 1 ignored                                               │
```

---

## Loading State

TMDB query progress appears in the tree panel's bottom border:

```
├── 0 staged / 7 total · TMDB 3/6 ──┤
```

Files awaiting TMDB results show only filename-extracted values in the detail
preview, with a dim indicator:

```
│ TMDB query pending...                                                          │
```
