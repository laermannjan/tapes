# Tapes — Design Document

**Date:** 2026-03-04
**Status:** Updated 2026-03-04 — P0/P1/P2 findings incorporated

---

## Overview

Tapes is a command-line tool for organising movie and TV show files. It fetches
metadata, renames and moves files into a clean directory structure, and maintains
a queryable local library. It is modelled after beets but targets video media.

Primary goal: file organisation.
Secondary goal: queryable library (what's missing, what do I have by a certain
director, etc.).

Target user: self-hosting, tech-savvy, comfortable editing a TOML config file.

---

## Architecture

```
CLI (typer + rich)
  └── Commands: import, move, check, modify, query, info, fields, stats, log
        └── Services: ImportService, LibraryService, QueryService
              └── Core: EventBus, Config, Database (SQLite)
                    └── Adapters: MetadataSource ABC, MediaType ABC
                          └── Built-in plugins + third-party via entry points
```

The query system is a plain Python library internally. The CLI is one consumer;
an LLM layer (future) will be another, calling the same functions.

---

## Database Schema

SQLite database at `~/.local/share/tapes/library.db` (XDG data home, or the
path set by `TAPES_DATA_DIR`). All tables use `INTEGER PRIMARY KEY AUTOINCREMENT`.

### `schema_version` table

Tracks the current schema version for migrations.

```sql
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);
```

On startup, tapes reads the version and runs any pending migration scripts in
order. Scripts live in `tapes/migrations/` and are numbered sequentially
(`002_add_genre.py`, etc.). `CREATE TABLE IF NOT EXISTS` is used for initial
creation; `ALTER TABLE` is used for additive changes.

### `items` table

One row per imported file.

```sql
CREATE TABLE items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    path           TEXT    NOT NULL,   -- absolute path on disk
    media_type     TEXT    NOT NULL,   -- "movie" | "tv"
    tmdb_id        INTEGER,
    title          TEXT,
    year           INTEGER,
    show           TEXT,               -- TV only
    season         INTEGER,            -- TV only
    episode        INTEGER,            -- TV only
    episode_title  TEXT,               -- TV only
    director       TEXT,               -- movie: primary director; TV: unused
    genre          TEXT,               -- comma-separated list (from TMDB)
    edition        TEXT,
    codec          TEXT,
    resolution     TEXT,
    audio          TEXT,
    hdr            INTEGER DEFAULT 0,
    match_source   TEXT,               -- "filename"|"folder"|"nfo"|"osdb hash"|"embedded tag"|"manual"
    confidence     REAL,
    mtime          REAL    NOT NULL,   -- file mtime at import (seconds since epoch)
    size           INTEGER NOT NULL,   -- file size in bytes at import
    imported_at    TEXT    NOT NULL    -- ISO-8601 timestamp
);
```

`director` and `genre` are stored here to support queries such as
`director:"David Lynch"` and `genre:thriller`.

### `seasons` table

Expected episode counts per show and season, populated from TMDB. Used by
`tapes query 'missing:episodes'` to determine collection completeness.

```sql
CREATE TABLE seasons (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_show_id   INTEGER NOT NULL,
    season_number  INTEGER NOT NULL,
    episode_count  INTEGER NOT NULL,
    UNIQUE (tmdb_show_id, season_number)
);
```

### `sessions` table

One row per import run.

```sql
CREATE TABLE sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT,
    state        TEXT    NOT NULL DEFAULT 'in_progress',  -- in_progress | completed | aborted
    source_path  TEXT    NOT NULL
);
```

### `operations` table

One row per file operation within a session. Drives both the session log and
interrupted-session resume.

```sql
CREATE TABLE operations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(id),
    source_path  TEXT    NOT NULL,
    dest_path    TEXT,
    op_type      TEXT    NOT NULL,   -- "copy" | "move" | "link" | "hardlink" | "skip"
    state        TEXT    NOT NULL DEFAULT 'pending',
    -- pending | copying | copied | db_written | source_deleted | done | failed
    item_id      INTEGER REFERENCES items(id),
    error        TEXT,
    updated_at   TEXT    NOT NULL
);
```

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `typer` | CLI framework |
| `rich` | Terminal output — tables, progress, interactive prompts |
| `guessit` | Filename parsing (title, year, S/E, resolution, source, codec, group) |
| `pymediainfo` | Technical metadata from file (codec, resolution, audio, HDR) |
| `sqlite3` | Stdlib — no ORM needed initially |
| `pydantic` | Config validation |
| `tomllib` | Stdlib (3.11+) — TOML config parsing |

Python 3.11+ required.

---

## Identification Pipeline

Per file, executed in order. Stops at the first high-confidence result.

```
1. Library DB record   → look up by (path, mtime, size); already imported? done immediately
2. tvshow.nfo          → show-level TMDB ID (TV only, walk up to 2 dir levels)
3. NFO / filename scan → imdb/tmdb ID in sidecar .nfo or filename → direct lookup
4. guessit             → parse filename + parent folder name
5. OpenSubtitles hash  → compute from file size + first/last 64KB
                         query OpenSubtitles → MovieReleaseName feeds title + group back in
6. MediaInfo           → actual codec, resolution, audio, embedded title tag as hint
7. TMDB query          → combine all signals into best query
8. Interactive fallback → below confidence threshold
```

The match source is recorded for every file (filename, folder, nfo, osdb hash,
embedded tag) and displayed during interactive import.

Note: xattr (filesystem extended attributes) is not used — it is not portable
across Windows and some network filesystems. The DB lookup (step 1) covers the
same use case: if a file at that path with that size and mtime is already in
the library, it is considered known.

### Confidence Scoring

Every candidate returned from TMDB is scored on a 0.0–1.0 scale (1.0 = certain
match). The score is a weighted combination:

| Signal | Score |
|---|---|
| OpenSubtitles hash match | 0.97 |
| NFO / filename contains TMDB or IMDb ID | 0.95 |
| Exact title + exact year | 0.90 |
| Exact title + year off by 1 | 0.75 |
| Exact title, no year available | 0.70 |
| Fuzzy title match (Jellyfish ratio > 0.85) + year | 0.65 |
| Fuzzy title match, no year | 0.50 |

If the top candidate scores ≥ `confidence_threshold` (default 0.9) it is
auto-accepted. Below that, tapes prompts interactively. The score is shown
in the interactive display (e.g., `94%`).

### OpenSubtitles Hash

The hash requires only the video file — no subtitle file needed. It is computed
from file size + first 64KB + last 64KB of the video. The OpenSubtitles response
includes `MovieReleaseName` (the original scene release filename), which tapes
uses for identification — unlike FileBot, which only uses the hash for subtitle
lookup.

Limitation: only works if someone has uploaded subtitles for that exact release
to OpenSubtitles. Falls back gracefully to guessit + TMDB.

---

## Discovery and Grouping

Tapes scans recursively from the given path. Directory structure is the primary
grouping signal, refined by identification results.

**Grouping rules:**
1. A directory whose files all identify as the same show/season → one group
2. A directory whose files identify as different things → split into sub-groups
3. Single movie file → its own group
4. Recurse into subdirectories when the parent does not form a coherent group

The user is never presented with a group that mixes content types. Unidentified
files are surfaced as a group to be skipped explicitly — tapes never silently
ignores a file.

---

## Interactive Import Flow

Groups are presented one at a time. High-confidence matches auto-proceed
(respecting `confidence_threshold`). The user is only interrupted for uncertain
or unidentified groups.

```
[1/8] The Wire/Season 01/  (12 files)
      → The Wire (2002)  tmdb:1438  [folder]

      E01  Pilot.mkv                  ✓  The Target      [filename]
      E02  The Detail.mkv             ✓  The Detail      [filename]
      E03  s01e03_rip.mkv             ✓  The Buys        [osdb hash]
      E04  108-wow.mkv                ✓  Old Cases       [embedded tag]
      E07  ✗ missing
      ...
      E12  Cleaning Up.mkv            ✓  Cleaning Up     [nfo]

      11 matched · 1 missing (E07) · 0 unmatched

       video     ✓  s01e01_pilot.mkv
       video     ✓  s01e02_the_detail.mkv
       ...
      subtitle   ✓  Subs/s01e01.en.srt
       unknown   ?  readme.txt           (not moved)

      [↵ accept] [e]edit files [a]accept-all [s]search [x]skip [q]quit   ← strong match

[2/8] Dune.2021.2160p.BluRay.mkv
      → Dune (2021)  tmdb:438631  94%  [filename]

       video     ✓  Dune.2021.2160p.BluRay.mkv
      subtitle   ✓  Dune.2021.en.srt
      subtitle   ✓  Subs/Dune.2021.nl.srt
       artwork   ✓  poster.jpg
        sample   ✗  sample.mkv           (ignored)

      [↵ accept] [e]edit files [a]accept-all [s]search [x]skip [q]quit   ← strong match

[3/8] blade.runner.mkv
      → multiple candidates:
        1. Blade Runner (1982)       tmdb:78      62%  [filename]
        2. Blade Runner 2049 (2017)  tmdb:335984  51%
      [1]accept [2]accept [↵ search] [m]metadata [x]skip [q]quit   ← ambiguous

[4/8] 108-wow.mkv
      → no match found
      [↵ search] [m]metadata [x]skip [q]quit                  ← no match
```

The `↵` key is highlighted in the terminal; other keys are dimmed.
Comments after `←` are for illustration only — not shown at runtime.
The companion file list is only shown when companion files are present in the group.

### Default action (Enter)

The default action bound to Enter changes with context. It is rendered in a
distinct colour (bold primary) in the terminal; the other options are shown
dimmed. This follows the beets convention — the highlighted option is what Enter
will do, but all other keys remain available.

| Situation | Default (Enter) |
|---|---|
| Single match, strong confidence (≥ 0.75, or gap to #2 ≥ 0.2) | Accept |
| Single match, low confidence | Search |
| Multiple auto-matched candidates, ambiguous | Search |
| Search results — one dominant result (gap ≥ 0.2) | Accept #1 |
| Search results — results are close together | *(no default; must type a number)* |
| No match found (first encounter) | Search |
| No match found (after a search that returned nothing) | Skip |
| Manual metadata confirmed | Accept |

**Auto-accept (no prompt):** confidence ≥ `confidence_threshold` → tapes
accepts automatically without showing the prompt at all. The prompt only appears
for sub-threshold cases (or when `--interactive` is set).

**Prompt shape varies by default:**

High-confidence sub-threshold (gap ≥ 0.2 between #1 and #2):
```
      [Dune (2021)  tmdb:438631  86%  [filename]]
      [↵ accept] [a]accept-all [s]search [x]skip [q]quit
```

Low-confidence or multiple candidates:
```
      1. Blade Runner (1982)       tmdb:78      62%
      2. Blade Runner 2049 (2017)  tmdb:335984  51%
      [1]accept [2]accept [↵ search] [m]metadata [x]skip [q]quit
```

No match, first time:
```
      → no match found
      [↵ search] [m]metadata [x]skip [q]quit
```

No match, after a search returned no results:
```
      → no results for "108 wow" (movie, 2013)
      [↵ skip] [m]metadata [s]try again [q]quit
```

`↵` denotes Enter; the highlighted option is the safe default for that
situation. Typing `A` is an alias for accept in any context where accept is
available.

### Search flow

Pressing `s` prompts for structured fields, then queries TMDB:

```
Media type [movie/tv]: movie
Title: The Wolf of Wall Street
Year (optional): 2013
More fields? [y/N]

Searching…
  1. The Wolf of Wall Street (2013)  tmdb:106646  0.95   ← dominant
  2. Wolf of Wall Street (1994)      tmdb:99999   0.41

[↵ 1]accept [2]accept [m]metadata [x]skip [q]quit
```

When one result is clearly dominant (gap ≥ 0.2), Enter defaults to accepting
it. When results are close together, there is no default — the user must type a
number:

```
  1. Movie A (2004)  tmdb:11111  0.68
  2. Movie A (2005)  tmdb:22222  0.61

[1]accept [2]accept [m]metadata [x]skip [q]quit        ← no ↵ default
```

Asking for title and year as separate fields (rather than a free-text query)
maps directly to TMDB query parameters and gives more reliable results.

If the search returns no results, the default shifts to skip (the user has
already made an effort; skipping is the safe next step):

```
→ no results for "wolf of wall street" (movie, 2013)
[↵ skip] [m]metadata [s]try again [q]quit
```

### Manual metadata entry

Pressing `m` (or `n` after a search returns no useful results) prompts for the
fields that drive template rendering. No TMDB lookup is performed.

```
Media type [movie/tv]: movie
Title: The Wolf of Wall Street
Year (optional): 2013
More fields? [y/N]

→ The Wolf of Wall Street (2013)  [manual]
[Enter] accept · [x] skip · [q] quit
```

**Carry-over:** when the user searched first, the fields already entered (media
type, title, year) are pre-filled. The user presses Enter to keep each value or
types a new one.

Manual metadata entry works identically in `--no-db` mode — the fields drive
template rendering; the DB write is simply skipped.

### Interactive prompt keys

| Key | Action |
|---|---|
| Enter | Accept best match (when single candidate shown) |
| `a` | Accept-all remaining groups above the confidence threshold |
| `e` | Edit companion file list for this group (toggle files on/off) |
| `s` | Search: collect structured fields, query TMDB |
| `m` | Enter metadata manually: fill fields directly, no TMDB lookup |
| `x` | Skip this group (recorded as skipped in session log) |
| `q` | Quit gracefully: emit `import_complete`, print summary |

### Match source labels

| Label | Meaning |
|---|---|
| `filename` | guessit parsed the filename |
| `folder` | parent folder name was the primary signal |
| `nfo` | NFO sidecar or tvshow.nfo contained an ID |
| `osdb hash` | OpenSubtitles hash matched |
| `embedded tag` | MKV/MP4 title tag used |
| `manual` | User supplied metadata fields directly |

Missing episodes are shown inline before the user accepts a group.

### Multi-episode files

When entering metadata for a TV episode, use the syntax `s01e01-e02` in the
episode field to specify a multi-episode file. Tapes names the file using the
`S01E01E02` convention, which Plex, Jellyfin, and Kodi all recognise.
Multi-episode handling is manual-only in v0.1 — tapes does not auto-detect
multi-episode files.

---

## File Operations and Metadata Writing

These are independent operations, configured separately.

```toml
[import]
mode  = "copy"   # copy | move | link | hardlink
write = true     # write NFO sidecar files
```

**File operation** — how the video file is physically handled.
**Metadata writing** — NFO sidecar files alongside the video. Handled by the
built-in `nfo` plugin (opt-in). Embedded container tags are opt-in via the
`convert` plugin.

NFO files are an output tapes can produce — not something it owns or keeps in
sync automatically. Users who want NFOs regenerated after a fix can do so
explicitly.

### Move Safety

Move mode is opt-in. Copy mode (the default) is inherently safe. For move mode,
tapes uses a copy-verify-then-delete sequence to prevent data loss:

```
1. Copy file to destination
2. Verify checksum (SHA-256) matches source
3. Write DB record (status: db_written)
4. Delete source file
5. Update DB record (status: done)
```

If tapes crashes at any step, the source file is still intact (steps 1–3) or
the DB record documents the state (steps 4–5). On next startup, tapes detects
any in-progress session and offers to resume.

Move mode is still riskier than copy mode — keep backups of irreplaceable files.

### tvshow.nfo

A `tvshow.nfo` at the show root directory contains the show-level TMDB ID.
Editing it and reimporting updates all episodes under that directory. This is
the primary mechanism for correcting a misidentified show.

---

## Companion Files

Every video group may include companion files: subtitles, artwork, NFO sidecars,
and others. Tapes classifies them, shows them grouped in the interactive display,
and moves/renames them alongside the video.

### Classification

Files are matched against category pattern lists in order. The first matching
category wins. `ignore` files are filtered before display and never offered for
selection.

| Category | Default patterns | Moved by default |
|---|---|---|
| `subtitle` | `*.srt *.ass *.vtt *.sub *.idx *.ssa` | yes |
| `artwork` | `poster.jpg folder.jpg fanart.jpg banner.jpg thumb.jpg` | yes |
| `nfo` | `*.nfo *.xml` | yes |
| `sample` | `sample.* *-sample.* *sample*.*` | no |
| `ignore` | `*.url *.lnk Thumbs.db .DS_Store` | never shown |
| `unknown` | *(everything else)* | no (opt-in) |

### Subdirectories

Companion files are discovered recursively within the source directory. Their
path relative to the video file is preserved at the destination:

```
source:       Dune.2021/Subs/Dune.2021.nl.srt
destination:  Dune (2021)/Subs/Dune (2021).nl.srt
```

### Renaming rules

| Category | Rename rule |
|---|---|
| `subtitle` | Replace stem, preserve language suffix and extension: `Film.en.srt` → `{dest_stem}.en.srt` |
| `nfo` | `{dest_stem}.nfo` |
| `artwork` | Moved as-is (same filename, new directory) — naming owned by the artwork plugin |
| `unknown` (opted in) | Moved as-is |

### Interactive edit mode

Pressing `e` at the group prompt opens a checklist. Space toggles a file;
Enter confirms. The `video` category is always on and cannot be toggled.

```
Edit companion files:
  [✓] Dune.2021.2160p.BluRay.mkv   video      (locked)
  [✓] Dune.2021.en.srt             subtitle
  [✓] Subs/Dune.2021.nl.srt        subtitle
  [✓] poster.jpg                   artwork
  [ ] sample.mkv                   sample
  [ ] making-of.txt                unknown
```

The `[e]` key appears only when companion files are present.

### Configuration

```toml
[companions]
subtitle = ["*.srt", "*.ass", "*.vtt", "*.sub", "*.idx", "*.ssa"]
artwork  = ["poster.jpg", "folder.jpg", "fanart.jpg", "banner.jpg", "thumb.jpg"]
sample   = ["sample.*", "*-sample.*", "*sample*.*"]
ignore   = ["*.url", "*.lnk", "Thumbs.db", ".DS_Store"]
# everything else → unknown

[companions.move]
subtitle = true
artwork  = true
nfo      = true
sample   = false
unknown  = false
```

---

## Collision Detection

Before any file operation — during both `import` and `tapes move` — tapes runs
a pre-flight pass that compares all planned destination paths against each other
and against the existing library. No files are touched until collisions are
resolved or dismissed.

### Type A — Template-only collision

Two or more items have different identities or technical specs but the current
template does not distinguish them.

```
⚠ Path collision — 2 files → Dune (2021)/Dune (2021).mkv

  A  Dune.2021.4K.HDR.mkv     2160p  HDR  x265  22 GB
  B  Dune.2021.BluRay.mkv     1080p  —    x264   8 GB

  Differ in: resolution, hdr, codec

  [k] keep A (higher quality, larger)
  [K] keep B
  [1] keep both — add {resolution}  →  Dune (2021) 2160p.mkv  /  Dune (2021) 1080p.mkv
  [2] keep both — add {source}      →  Dune (2021) BluRay.mkv  /  Dune (2021) WEBRip.mkv
  [c] keep both — custom suffix
  [x] skip both
```

The chosen disambiguation is a one-time addition for those specific files only.
The config template is not modified.

### Type B — Likely-duplicate collision

Items appear to be the same content (same metadata and similar technical specs).

```
⚠ Likely duplicate — 2 files → Dune (2021)/Dune (2021).mkv

  A  dune-2021-4k.mkv    2160p  HDR  22.1 GB
  B  Dune.2021.4K.mkv    2160p  HDR  22.0 GB

  [A] keep A (larger)
  [B] keep B (smaller)
  [c] keep both — custom suffix
  [x] skip both
```

### Scope

| Operation | Checks |
|---|---|
| `import` | Incoming files against each other; incoming against existing DB records |
| `tapes move` | Re-rendered paths against each other; against non-DB files on disk |

Collisions involving three or more files are presented together as a group.

---

## Templates

Separate template per media type. `{field}` syntax. Defaults are
Plex/Jellyfin-compatible.

```toml
[templates]
movie = "{title} ({year})/{title} ({year}){ext}"
tv    = "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d} - {episode_title}{ext}"
```

**Available fields:**

| Source | Fields |
|---|---|
| TMDB | `title`, `year`, `show`, `season`, `episode`, `episode_title`, `genre`, `director`, `rating` |
| guessit (filename) | `source` (BluRay/WEBRip/etc.), `group` (release group) |
| MediaInfo (file) | `codec`, `audio`, `resolution`, `hdr` |
| Computed | `ext`, `quality` (normalised: 720p/1080p/4K) |

MediaInfo values take precedence over guessit for technical fields — guessit
gives hints from the filename, MediaInfo gives facts from the file.

`{edition}` is populated from guessit when the filename contains edition markers
(e.g., `Director.Cut`, `Extended`, `Theatrical`). Use it in templates to
distinguish multiple versions of the same film:

```toml
movie = "{title} ({year}){edition: - $}{ext}"
# → Dune (2021) - Director's Cut.mkv   (when edition present)
# → Dune (2021).mkv                    (when absent)
```

Optional fields render as empty string if missing. Users can inspect available
fields with:

```bash
tapes fields                  # list all fields
tapes fields movie.mkv        # show actual values for a specific file
```

---

## Plugin System

### Discovery

Tapes discovers plugins at startup via Python entry points
(`importlib.metadata`). Built-in plugins ship with the package. Third-party
plugins declare themselves under the `tapes.plugins` group:

```toml
# third-party plugin's pyproject.toml
[project.entry-points."tapes.plugins"]
plex = "tapes_plex.plugin:PlexPlugin"
```

Users install via pip and enable in config. No dotted paths visible to users.

### Activation

Each plugin is enabled via its config section. No global plugin list needed.

```toml
[artwork]
enabled = true
destination = "folder"

[subtitles]
enabled = true
languages = ["en", "nl"]

[nfo]
enabled = false

[nfo.tv]
enabled = true     # enabled for TV only
```

### Per-Media-Type Config

Base config with per-type overrides. The merge is a shallow override — any key
in the media-type section overrides the base; everything else inherits.

```toml
[convert]
codec              = "x265"
target_resolution  = "1080p"

[convert.tv]
target_resolution  = "720p"   # override for TV only

[subtitles]
languages = ["en", "nl"]

[subtitles.movies]
languages = ["en"]
```

### Events

```python
class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, fn: Callable):
        self._listeners[event].append(fn)

    def emit(self, event: str, **kwargs):
        for fn in self._listeners[event]:
            try:
                fn(**kwargs)
            except Exception as exc:
                logger.error(
                    "Plugin error: handler %s for event %s raised %s: %s",
                    fn.__qualname__, event, type(exc).__name__, exc,
                )
```

A buggy or crashing plugin handler logs an error and is skipped. The import
continues for the current file and all subsequent files.

| Event | Payload | Used by |
|---|---|---|
| `before_match` | `file_info` | Filename enrichment, custom matchers |
| `after_match` | `file_info, match` | Metadata enrichment |
| `before_write` | `item` | Scrub, duplicate check |
| `after_write` | `item` | Artwork, subtitles, NFO, Plex refresh |
| `on_no_match` | `file_info` | Logging, fallback |
| `on_duplicate` | `item, existing` | Duplicate handling |
| `import_complete` | `items` | Webhooks, summaries |

### Built-in Plugins

| Plugin | Event hook | Purpose |
|---|---|---|
| `artwork` | `after_write` | Download poster/fanart from TMDB |
| `subtitles` | `after_write` | Download from OpenSubtitles |
| `nfo` | `after_write` | Write NFO sidecar files |
| `scrub` | `before_write` | Strip embedded metadata from file |
| `convert` | `after_write` | Remux or transcode via FFmpeg |

All built-in plugins default to `enabled = false`. Opt-in only.

---

## CLI Commands

```bash
tapes --config ~/tapes-movies.toml import <path>   # override config for this run

tapes import <path>                    # import files from path
tapes import <path> --dry-run          # preview without changes
tapes import <path> --interactive      # force interactive for every group
tapes import <path> --no-db            # identify and rename only, no DB or session log
tapes import <path> --mode move        # override config mode for this run
tapes import <path> --confidence 0.7   # lower threshold for this run

tapes move                             # re-apply templates to all library files
tapes move --dry-run                   # preview renames without moving anything

tapes check                            # validate library integrity
                                       # detects: missing files, DB path mismatches,
                                       # library root changes

tapes query 'director:"David Lynch"'
tapes query 'year:>2000 genre:thriller'
tapes query 'missing:episodes show:"The Wire"'

tapes info <file>                      # show metadata — runs pipeline if file not in DB
tapes fields                           # list available template fields
tapes fields <file>                    # show actual field values for a file
tapes stats                            # library summary

tapes modify <path>                    # correct a wrong match interactively
tapes modify <path> --id tmdb:438631   # supply a known TMDB ID directly
tapes modify <path> --no-move         # update DB only, do not rename file on disk

tapes log                              # last session: summary (counts + unmatched files)
tapes log --full                       # last session: full file list with source → dest
tapes log <session-id>                 # specific past session
```

---

## Configuration Reference

```toml
[library]
movies = "~/Media/Movies"
tv     = "~/Media/TV"

[import]
mode                 = "copy"    # copy | move | link | hardlink
write                = true      # write NFO sidecars
confidence_threshold = 0.9       # below this → interactive
interactive          = false     # force interactive for all groups
dry_run              = false

[metadata]
movies      = "tmdb"
tv          = "tmdb"
tmdb_api_key = ""    # or set env var TMDB_API_KEY

[templates]
movie = "{title} ({year})/{title} ({year}){ext}"
tv    = "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d} - {episode_title}{ext}"

[artwork]
enabled     = true
destination = "folder"

[subtitles]
enabled   = true
languages = ["en", "nl"]

[subtitles.movies]
languages = ["en"]

[nfo]
enabled = false

[nfo.tv]
enabled = true

[convert]
enabled           = false
codec             = "x265"
target_resolution = "1080p"

[convert.tv]
target_resolution = "720p"

[replace]
": " = " - "
"/"  = "-"

[companions]
subtitle = ["*.srt", "*.ass", "*.vtt", "*.sub", "*.idx", "*.ssa"]
artwork  = ["poster.jpg", "folder.jpg", "fanart.jpg", "banner.jpg", "thumb.jpg"]
sample   = ["sample.*", "*-sample.*", "*sample*.*"]
ignore   = ["*.url", "*.lnk", "Thumbs.db", ".DS_Store"]
# everything else → unknown

[companions.move]
subtitle = true
artwork  = true
nfo      = true
sample   = false
unknown  = false
```

---

## Library Integrity and Root Changes

Each media type has its own configured root:

```toml
[library]
movies = "~/Media/Movies"
tv     = "~/Media/TV"
```

### tapes check

Validates that every DB record has a corresponding file on disk. Reports:
- Missing files (in DB, not on disk)
- Orphaned files (on disk at the library root, not in DB — video files only)
- Library root mismatches (configured path differs from what was last used)

When a root mismatch is detected, tapes matches existing files to DB records
by TMDB ID + episode info, then bulk-updates paths:

```
Library root changed:
  movies: ~/Media/Movies → /mnt/nas/Movies
Found 243/247 files at new root. 4 missing.
Update database paths? [Y/n]
```

The 4 missing files are listed so the user can investigate. `check` is
read-only except for the path bulk-update on confirmed root mismatch.

Manual-import records (`match_source = "manual"`, no TMDB ID) that cannot be
matched by TMDB ID are matched by title + year + media type instead. If still
unmatched, they are listed separately so the user can investigate.

### tapes move

Re-applies current templates to all library items, moving files to new paths.
Used when the user changes a template or library root in config.

**Step-by-step:**

```
1. LOAD        Read all items from DB → (item, current_path) list
2. RENDER      Re-render template for each item with current config
3. DIFF        Keep only items where current_path ≠ new_path
               Items already at the correct path are no-ops; shown in summary
4. COMPANIONS  For each planned video move, identify companion files with same
               stem (subtitles, artwork, NFOs) using the companion rules;
               apply the same renaming rules as import
5. PRE-FLIGHT  Collision detection across all planned new paths:
               a. Two items → same new_path (collision group)
               b. new_path already belongs to a different DB item
               c. new_path exists on disk but is not in the DB (orphan conflict)
               → Resolve each collision group interactively before proceeding
6. PREVIEW     Print summary (and exit if --dry-run):
               "143 to move  ·  62 already in place  ·  2 collisions resolved"
               Table of old → new paths for items that will change
7. CONFIRM     "Move 143 files? [y/N]"  ← default N; scale warrants caution
8. EXECUTE     For each planned move:
               - Same filesystem: os.rename() — atomic, no copy-verify needed
               - Cross-filesystem: copy → SHA-256 verify → delete source
               - Move companion files alongside the video (preserving subdir structure)
               - Update DB path record
               - Missing source file: log warning, skip item, continue (never abort)
               - Unexpected destination collision: log warning, skip item, continue
9. REPORT      "143 moved  ·  2 skipped (missing source)  ·  0 failed"
               "Run `tapes check` for details on skipped files."
```

**Session tracking:** `move` sessions use states `pending → moving → done | failed | skipped`.
If interrupted, re-running `tapes move` re-diffs from scratch — items already
at their new path show as no-ops, providing natural resume without explicit
recovery.

**`--dry-run` output:**

```
Would move 42 files (205 already in place):

  The Wire (2002)/Season 01/The Wire (2002) - S01E01 - The Target.mkv
    ← The Wire/Season 01/s01e01_pilot.mkv

  Dune (2021)/Dune (2021).mkv
    (no change)

  ...

⚠ 2 collisions detected — resolve interactively (run without --dry-run)
```

**Warning — `--no-db` imports:** Files imported with `--no-db` are not in
the DB and are invisible to `tapes move`. If you mix tracked and `--no-db`
imports, `move` will not relocate the untracked files. `tapes import --no-db`
prints this warning at completion.

### tapes modify

Corrects the metadata for an already-imported item. Like `beet modify`, it
updates the DB record and renames the file on disk when the path changes.

```bash
tapes modify <path>                    # interactive: shows current match, search TMDB
tapes modify <path> --id tmdb:438631   # supply a known TMDB ID directly
tapes modify <path> --no-move         # update DB only, do not rename file
```

`<path>` can be a single file, a season directory, or a show directory.
When a directory is given, all items under it are updated.

**Step-by-step (interactive):**

```
1. Look up <path> in DB — if not found, report clearly and exit
   (tapes modify does not import new files; use tapes import for that)
2. Show current metadata and file path
3. Present the standard search/metadata prompt (same keys as import):
   search TMDB, enter a TMDB ID directly, or enter metadata manually
4. Update DB record with new metadata
5. Re-render template → compute new_path
6. If new_path ≠ current_path:
   - Show: "Rename: old/path.mkv → new/path.mkv"
   - If same filesystem: os.rename() (atomic)
   - If cross-filesystem: copy → verify → delete source
   - Update DB path
   (Skipped if --no-move is passed)
7. Companion files: rename/move alongside the video (same rules as import)
8. Emit after_write event so plugins can regenerate NFOs, artwork, etc.
```

**Directory argument:** When `<path>` is a season or show directory, each
file is updated sequentially using the same interactive flow. If a single TMDB
ID is supplied via `--id`, it is applied to all files in the directory — tapes
validates that the ID is appropriate for the media type and prompts for
confirmation before bulk-updating.

### --no-db mode

`tapes import --no-db` runs the full identification and file operation pipeline
without writing anything to the database or session log. Useful for:
- One-off renaming jobs not meant to be tracked
- Users who only want the matching and renaming functionality
- Preprocessing files before a proper import

All other flags (`--dry-run`, `--interactive`, `--mode`, `--confidence`) work
normally with `--no-db`.

**Limitation:** Files imported with `--no-db` are not tracked. `tapes move`,
`tapes check`, and `tapes query` will not see them. This is printed as a
warning at the end of every `--no-db` run.

---

## CLI Flags vs Config

**CLI flags** — override config for a single invocation. Used for things that
vary per run:

| Flag | Commands |
|---|---|
| `--config <path>` | all (global) |
| `--dry-run` | `import`, `move` |
| `--interactive` | `import` |
| `--no-db` | `import` |
| `--mode copy\|move\|link\|hardlink` | `import` |
| `--confidence <0.0–1.0>` | `import` |
| `--full` | `log` |
| `--no-move` | `modify` |
| `--id tmdb:<id>` | `modify` |

**Config only** — structural setup that does not change run to run:
library paths, templates, plugin settings, replace rules, metadata sources.

The rule: if you'd plausibly want to override it once without changing your
config permanently, it's a CLI flag. Otherwise, config only.

---

## Session Log

Every import session is recorded in the database. Sessions can be resumed if
interrupted.

**Session states:** `in_progress` | `completed` | `aborted`

**Per-file operation states:**

```
pending → copying → copied → db_written → source_deleted → done
                                        ↘ failed
```

On startup, tapes checks for sessions in `in_progress` state:

```
Found interrupted import session from 2026-03-04 14:32
  47 files completed, 3 copying, 156 pending
Resume? [Y/n]
```

Resume behaviour:
- `done` files — skipped
- `copying` files — re-copy from source (partial destination discarded)
- `copied` / `db_written` files — complete the remaining steps
- `pending` files — process normally

`tapes log` displays two views of session data:

- **Default (summary):** counts only — N imported, N skipped, N failed, N
  unmatched. Lists unmatched files so the user can act on them.
- **`--full`:** every file operation with source → destination path, status,
  and match source. Suitable for auditing or debugging a large import.

---

## Filename Sanitization

After template rendering, tapes sanitizes the output path to remove characters
that are illegal or problematic on common filesystems. By default, tapes makes
filenames safe for all platforms (including Windows and SMB shares).

Default replacements (configurable via `[replace]`):

| Pattern | Replacement |
|---|---|
| `/ \` (path separators in field values) | `-` |
| `: ` (colon + space, e.g. "Mission: Impossible") | ` - ` |
| `:` (colon without space) | `-` |
| `<>"\?\*\|` (Windows reserved) | `` (removed) |
| Control characters (0x00–0x1f) | `` (removed) |
| Trailing dots and whitespace | `` (removed) |

Users can override via the `[replace]` config section:

```toml
[replace]
": " = " - "
"/" = "-"
```

---

## API Stability

Tapes uses `0.x` versioning. Interfaces exist and are documented but carry no
stability guarantees until `1.0`. Users building on the extension interfaces do
so at their own risk until then.

Extension points that will be stabilised at `1.0`:
- `MetadataSource` ABC
- `MediaType` ABC
- EventBus event signatures
- Entry point group name (`tapes.plugins`)
