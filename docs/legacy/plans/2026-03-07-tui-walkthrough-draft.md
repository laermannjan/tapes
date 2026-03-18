# Tapes TUI Walkthrough (Draft)

A draft walkthrough of tapes from the user's perspective. Not a readme
yet -- just the workflows and use cases in prose.

---

## The basics

Point tapes at a directory of movie and TV files. It scans everything,
extracts metadata from filenames, queries TMDB for matches, and presents a
file tree showing where each file will end up in your library.

```
tapes import ~/downloads/movies
```

The screen splits into two areas. The file tree occupies most of the space.
A small detail panel at the bottom previews metadata for the file under your
cursor.

```
┌─ Files ─────────────────────────────────────────────────────────────────┐
│ ✓ Breaking.Bad.S01E01.720p.BluRay.x264.mkv   → Breaking Bad (2008)/…  │
│ ✓ Breaking.Bad.S01E02.720p.BluRay.x264.mkv   → Breaking Bad (2008)/…  │
│ ○ Inception.2010.1080p.mkv                    → Inception (2010)/…     │
│ ○ The.Matrix.1999.720p.mkv                    → The Matrix (1999)/…    │
├─ Detail ────────────────────────────────────────────────────────────────┤
│ Inception.2010.1080p.mkv  → Inception (2010)/Inception (2010).mkv      │
│ title: Inception  year: 2010  type: movie                  TMDB 92%    │
└─────────────────────────────────────────────────────────────────────────┘
```

Each file has a marker:

- **✓** (green) -- staged. Tapes will process this file when you commit.
- **○** (yellow) -- unstaged. Check the destination before staging.
- **·** (dim) -- ignored. Tapes will skip this file entirely.

The arrow shows the destination path -- where the file will land in your
library. The destination matters most. If it looks right, stage the file
and move on.

---

## The happy path

Most of the time, tapes identifies files correctly. It auto-accepts TMDB
matches with high confidence and stages those files. Your job: scan the list,
verify the destinations, and commit.

1. Scan the file tree. Green checkmarks mean tapes matched with confidence.
2. Spot-check a few destinations. Do the titles, years, and episode numbers
   look right?
3. Press `c` to commit. A confirmation dialog shows exactly what will
   happen -- which files go where. Press `y` to proceed.

For files that remain unstaged (yellow circles), you have three options:

- If the destination looks right, press `space` to stage it.
- If something looks wrong, press `enter` to open the detail view and fix it.
- If you want to skip a file entirely, press `x` to ignore it.

Press `a` on any file to accept its best TMDB match manually. This helps when
confidence falls just below the auto-accept threshold.

---

## Fixing metadata in the detail view

Press `enter` on a file to open the detail view. The bottom panel expands to
show full metadata: your current result on the left, a TMDB source on
the right.

```
┌─ Files ─────────────────────────────────────────────────────────────────┐
│ ✓ Breaking.Bad.S01E01.720p.mkv   → Breaking Bad (2008)/S01E01.mkv     │
│ ○ Inception.2010.1080p.mkv       → Inception (2010)/Inception.mkv     │
├─ Detail ────────────────────────────────────────────────────────────────┤
│ Inception.2010.1080p.BluRay.x264-GROUP.mkv                             │
│ → Inception (2010)/Inception (2010).mkv                                │
│ ────────────────────────────────────────────────────────────────────    │
│              result                    TMDB #1 (92%)           [1/2]   │
│ ────────────────────────────────────────────────────────────────────    │
│  title       Inception                 Inception                       │
│  year        2010                      2010                            │
│  media_type  movie                     movie                           │
│  codec       x264                      ·                               │
│  source      BluRay                    ·                               │
└─────────────────────────────────────────────────────────────────────────┘
```

Colors reveal the state of each field at a glance:

- **Dim** values match your result. Nothing to change.
- **Yellow** values differ from your result. Applying this source would
  overwrite them.
- **Green** values would fill an empty field in your result.

Press `h` and `l` to cycle through TMDB sources. The `[1/2]` indicator shows
which source you are viewing. Each source has a confidence percentage -- higher
means a stronger match.

### Applying values

- Press `enter` on a field row to apply that single value from the source.
- Press `shift+enter` to apply all values from the current source.

The destination path at the top updates live as you change fields.

### Editing and clearing

- Press `e` to edit a result field directly. An inline text input appears.
  Type the new value, press `enter` to confirm, or `esc` to cancel.
- Press `d` to clear a field.
- Press `D` to reset a field to what the filename parser originally extracted.
- Press `u` to undo any change.

Press `esc` to return to the file tree.

---

## Bulk fixes with multi-select

Sometimes several files share the same problem. A TV show may have a
misspelled title across all episodes, or a movie and its subtitle files may
all match the wrong TMDB entry. Fix them together instead of one by one.

### Selecting files

Press `v` to start a range selection, then move the cursor to extend it. Or
select files individually. With your selection ready, press `enter` to open
the detail view.

### The shared detail view

The detail view works the same way, but now operates on all selected files
at once. The header shows how many files you selected. Fields that match
across all files display normally. Fields that differ show `(N values)`.

```
├─ Detail ────────────────────────────────────────────────────────────────┤
│ 8 files selected                                                       │
│ ────────────────────────────────────────────────────────────────────    │
│              shared result             TMDB #1 (88%)           [1/3]   │
│ ────────────────────────────────────────────────────────────────────    │
│  title       Baking Bad               Breaking Bad                     │
│  year        ·                         2008                            │
│  media_type  tv                        tv                              │
│  season      1                         ·                               │
│  episode     (8 values)                                                │
│  ep_title    (8 values)                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

Every operation applies to all selected files:

- **Apply a source** -- sets the shared identity fields (title, year) on all
  files at once.
- **Edit a field** -- the value you type overwrites that field on every
  selected file.
- **Clear or reset** -- affects all selected files.

### Example: fixing a misspelled TV show

Your downloads folder has `Baking.Bad.S01E01.mkv` through
`Baking.Bad.S01E08.mkv`. The filenames contain a typo, so TMDB either
returned no match or matched the wrong show.

1. Select all 8 files with `v`.
2. Press `enter` to open the detail view. The shared result shows
   `title: Baking Bad`.
3. Press `e` on the title field. Type `Breaking Bad`. Press `enter`.
4. Press `r` to re-query TMDB with the corrected title.
5. TMDB returns "Breaking Bad (2008)." Press `shift+enter` to apply.
6. Title, year, and TMDB ID update on all 8 files. Episode matching runs
   automatically -- each file's episode number gets matched against the
   show's episode list from TMDB, filling in episode titles.
7. Press `esc` to return to the tree. All 8 files now show correct
   destinations.

### Example: movie with companions misidentified

You have `Inception.mkv`, `Inception.en.srt`, and `Inception.poster.jpg`.
All three matched the wrong TMDB movie.

1. Select all 3 files.
2. Open the detail view. The shared result shows the wrong title.
3. Cycle through TMDB sources with `l` to find the correct one, or edit the
   title and re-query.
4. Apply the correct source. All 3 files update.
5. Back in the tree, all three files now point to the right movie folder.

### Example: wrong season number

The filename parser read the episode number as the season number on all
files. The shared result shows `season: (8 values)` because each file
received a different "season."

1. Select all affected files.
2. In the detail view, press `e` on the season field.
3. Type the correct season number. Press `enter`.
4. All files now carry the right season. Re-query TMDB if needed.

### Example: re-identifying a whole show across seasons

All four seasons of a show matched the wrong TMDB entry. You want to fix
them all at once.

1. Select all files across all seasons.
2. The shared result shows `title: Wrong Show`, `season: (various)`,
   `episode: (various)`.
3. Edit the title to the correct show name. Re-query TMDB.
4. Apply the right match. Title, year, and TMDB ID update on all files.
   Season and episode numbers stay unchanged (they were correct -- only the
   show identity was wrong). Episode matching runs per-file.
5. Every file across all four seasons now has the correct destination.

---

## Other features

### Search and filter

Press `/` to search. Type a query and the file tree filters live, showing
only matching files. Press `enter` to confirm the filter or `esc` to cancel
and restore the full list.

### Flat mode

Press `` ` `` to toggle between tree mode (folder hierarchy) and flat
mode (all files listed without folders, paths relative to the import
directory).

### Ignoring files

Press `x` to toggle a file as ignored. Ignored files appear dimmed and tapes
will skip them. Useful for sample files, unwanted extras, or files you plan
to handle later.

### Committing

Press `c` when ready. A confirmation dialog lists every staged file and its
destination. Review the list, then press `y` to proceed or `n` to cancel.
Tapes copies, moves, or symlinks files to your library according to your
configuration.

### Help

Press `?` to see all available shortcuts and a brief explanation of how
staging and sources work.
