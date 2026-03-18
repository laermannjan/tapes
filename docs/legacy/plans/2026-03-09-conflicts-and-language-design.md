# Conflict Resolution and TMDB Language Support

## Goal

Two independent improvements: (1) detect and auto-resolve file destination
conflicts before committing, and (2) support TMDB language setting for
localized titles in output.

## 1. Conflict Detection and Resolution

### Problem

No pre-commit validation exists. Two staged files mapping to the same
destination silently fail at processing time. Files already existing at the
destination produce a generic error. The user has no warning and no
understanding of what went wrong.

### Design

When the user enters the commit view, compute file pairs and run three checks
before displaying anything:

**Destination writability.** For each unique destination directory, walk up to
find the first existing ancestor and check `os.access(ancestor, os.W_OK)`.
Always on -- no config toggle. Unwritable destinations are reported as
blocking problems; affected files are skipped.

**Duplicate destinations (same-size files).** Group pairs by destination path.
Within each group, compare file sizes. Same-size files are presumed
duplicates. Auto-resolution: keep the file with the most populated `result`
dict (most metadata fields filled), unstage the rest.

**Disambiguation (different-size files, same destination).** Different files
mapping to the same destination get a disambiguating suffix. The first file
(alphabetical by source path) keeps the original name. Subsequent files get
`-2`, `-3`, etc. appended to the stem, preserving `full_extension()`. Also
applies to files whose destination already exists on disk.

### Config

Two settings in a new `ConflictConfig` (or fields on existing config):

- `duplicate_resolution`: `auto` | `warn` | `off` (default: `auto`)
- `disambiguation`: `auto` | `warn` | `off` (default: `auto`)

`auto` resolves and informs. `warn` shows conflicts but does not resolve; user
must go back and fix manually. `off` skips the check entirely (current
behavior).

### Commit View Display

Conflict report appears inline, above the stats, only when conflicts exist:

```
  2 conflicts resolved:

    check Unstaged duplicate: Movie.mkv (same as /other/Movie.mkv)
    check Disambiguated: Show S01E01.mkv -> Show S01E01-2.mkv

  1 problem:

    x Cannot write to /media/Movies -- check permissions
       3 file(s) skipped
```

- Auto-resolved conflicts: check prefix, muted style (informational).
- Blocking problems: x prefix, error style.
- Stats and "enter to confirm N files" reflect only processable files.
- Enter always works -- commits whatever is valid, skipping problem files.
- Clean commits (no conflicts) render exactly as today.

### FileExistsError improvement

`process_file` currently raises a generic `FileExistsError`. The error
message in `process_staged` should include "already exists" detail instead of
the generic "Error processing" text.

## 2. TMDB Language Support

### Problem

All TMDB API calls return data in TMDB's default language (typically English).
Users who want localized titles (e.g. German, French) have no way to
configure this.

### Design

**Config.** Add `language: str = ""` to `MetadataConfig`. Empty string means
no language param sent (current behavior). When set (e.g. `de`, `de-DE`,
`fr`), passed to all three TMDB endpoints. CLI flag: `--language`.

**API layer.** `search_multi`, `get_show`, `get_season_episodes` gain an
optional `language` parameter. When non-empty, included in the request params
dict.

**Response parsing.** TMDB always returns both `original_title`/`original_name`
and `title`/`name` regardless of language setting. Store the localized title
in Source `fields["title"]` (used for display and destination). Store
`original_title` alongside for scoring purposes.

**Similarity scoring.** `compute_similarity` scores the guessit-extracted
title against both `original_title` and the localized `title`, takes the max.
This handles filenames in either language -- an English-named file matches a
German result via `original_title`, and a German-named file matches via the
localized `title`.

**Search behavior.** TMDB's `search/multi` matches against titles in all
languages regardless of the `language` parameter. The parameter only controls
the response language. So passing `language=de` does not reduce search
coverage.

## 3. Data Flow

### Commit flow

```
User presses 'c' (commit)
  |
  +-- Compute file pairs (as today)
  +-- Run conflict detection:
  |    +-- Check destination writability (os.access on ancestors)
  |    +-- Detect duplicate destinations (group by dest, compare sizes)
  |    |    +-- Same size: auto-unstage lesser node (fewer result fields)
  |    |    +-- Different size: auto-disambiguate with -2, -3 suffixes
  |    +-- Check for pre-existing files at destination
  |         +-- Auto-disambiguate with suffix
  |
  +-- Apply auto-resolutions (if config is 'auto')
  +-- Recompute stats from remaining valid pairs
  |
  +-- Show commit view:
       +-- Conflict report (resolved and problems)
       +-- Stats (reflecting only processable files)
       +-- Library paths
       +-- "enter to confirm N files" / "esc to cancel"
```

### TMDB language flow

```
guessit extracts title from filename
  |
  +-- search_multi(query, language=config.language)
       |
       +-- Returns: title (localized), original_title
       +-- Scoring: max(similarity(query, title), similarity(query, original_title))
       |
       +-- get_show / get_season_episodes(language=config.language)
            |
            +-- Source fields populated with localized titles
```

## 4. Testing

**Conflict detection:** duplicate detection (same size unstages lesser, different
size disambiguates), suffix logic preserves full_extension, pre-existing file
detection, permission check, config modes (auto/warn/off).

**Commit view rendering:** conflict report appears only when conflicts exist,
resolved vs problem styling, stats reflect processable count, clean commit
unchanged.

**TMDB language:** language param included/omitted based on config, similarity
scoring takes max of original and localized, original_title stored in Source.

**FileExistsError:** specific error message preserved through process_staged.
