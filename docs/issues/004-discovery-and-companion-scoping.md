# Discovery and Companion Scoping

**Date:** 2026-03-05
**Status:** Analysis -- ready for review
**Triggered by:** importing from the project root scanned every file in the repo

---

## The incident

Running `tapes import .` from the repository root produced two failures:

1. **Companion explosion.** Every non-video file in the entire directory tree
   (`.py`, `.md`, `.toml`, `__pycache__/`, `.git/`) was listed as a companion.
   Git pack index files (`.idx`) matched the VobSub subtitle pattern and were
   queued for copy with `move_by_default: True`.

2. **Self-import.** A video already inside the configured library was found by
   the scanner, matched by TMDB, and `copy_verify` failed with "same file" when
   source and destination resolved to the same path.

Both are symptoms of the same gap: tapes has no model of what constitutes a
reasonable import source. It trusts the input path completely and applies
unbounded recursive scanning to everything beneath it.

---

## What tapes assumes today

Implicitly, the code assumes the user points tapes at one of:

- A **single video file** (`tapes import Movie.mkv`)
- A **release folder** (`tapes import ~/downloads/Movie.2021.1080p/`)
- A **downloads directory** one level deep (`tapes import ~/downloads/`)

The scanner and companion classifier were written for these cases. They break on
anything outside that model:

| Input | Scanner | Companion classifier |
|---|---|---|
| Single file in clean dir | OK | Scans parent recursively -- picks up unrelated files |
| Release folder | OK | OK -- folder is dedicated to the video |
| Downloads dir (flat) | OK | Scans entire dir recursively per video |
| Project root / home dir | Enters `.git`, `node_modules`, `.venv` | Lists every file in the tree |
| Path inside the library | Finds already-imported files | Finds already-imported companions |

---

## The input directory model

Tapes needs an explicit model of what it will and will not scan. This model has
three layers: what directories to enter, what files to consider as videos, and
what files to consider as companions.

### Layer 1: Directory traversal

The scanner decides which directories to enter during `rglob`. It currently
enters everything. It should skip:

**Always skip (hardcoded):**
- Hidden directories (name starts with `.`): `.git`, `.svn`, `.hg`, `.DS_Store`
  folders, `.Spotlight-V100`, `.fseventsd`, etc.
- Python bytecode: `__pycache__`
- Common non-media trees: `node_modules`, `.venv`, `venv`, `.tox`, `.mypy_cache`

These directories never contain video media in any reasonable scenario. Entering
them is pure waste and risk.

**Skip by default (configurable):**
- The library directories themselves (`library.movies`, `library.tv`). Importing
  from inside the library is almost certainly a mistake. If someone genuinely
  wants to re-import from the library, they can pass `--no-skip-library` or
  configure it off.

**Skip by user config (new `import.exclude` list):**
- Glob patterns the user adds to `tapes.toml`, e.g. `["Backups/*", "*.tmp"]`.
  Default empty.

### Layer 2: Video file filtering

The scanner already filters by extension and sample pattern. Two issues remain:

**Extension set mismatch.** `discovery/scanner.py` defines `VIDEO_EXTENSIONS`
with `.wmv` and `.flv`. `companions/classifier.py` defines its own copy without
those two. This is a latent bug: a `.wmv` file is discovered as a video by the
scanner but not excluded as a video by the companion classifier, so it could
appear as an `UNKNOWN` companion of another video in the same directory.

There should be one canonical `VIDEO_EXTENSIONS` set imported everywhere.

**No upper bound on file count.** If someone runs `tapes import /` there is no
circuit breaker. Worth logging a warning above some threshold (e.g., 1000 video
files) but not blocking -- the user may have a large collection.

### Layer 3: Companion scoping

This is where the current code fails most visibly. The companion classifier
needs a notion of **scope** -- how far from the video file it should look for
related files.

**Release folder model.** When a video is inside a subfolder of the import root,
that subfolder is its "release folder." The classifier should scan it
recursively (to find `Subs/`, `Extras/`, etc.). This is the common case for
organized downloads.

**Flat directory model.** When a video sits directly in the import root (no
enclosing subfolder), the classifier should scan only the immediate directory --
no recursion. Same-directory `.srt` and `.nfo` files are found; deep nested
unrelated files are not.

**Single file model.** When the import path is a single file, the import root is
that file's parent. Same rules as flat directory apply: scan the immediate
directory only.

These three cases cover every reasonable input:

```
tapes import ~/downloads/
  downloads/
    Movie.2021.1080p/          <-- release folder: recursive scan
      Movie.2021.1080p.mkv
      Subs/
        Movie.en.srt           <-- found
    other-movie.mkv            <-- flat: same-dir only
    other-movie.en.srt         <-- found
    taxes/
      2024.pdf                 <-- NOT scanned

tapes import movie.mkv         <-- single file: same-dir only
```

---

## Same-file and library overlap

Separate from scoping, tapes needs guards against importing files that are
already where they belong:

1. **Same-file detection.** Before any file operation, resolve both source and
   destination to absolute paths and compare. If identical, skip with a clear
   message -- not an error.

2. **Library overlap detection.** Before scanning, check whether the import path
   is inside (or equal to) a configured library directory. If so, warn and
   require explicit confirmation or a flag. This catches `tapes import .` when
   cwd is the library.

3. **Already-imported detection.** The DB cache (path + mtime + size) already
   handles re-imports gracefully -- the file is recognized and skipped. But this
   only works when the DB has the record. A `--no-db` import into the library
   would not catch it.

---

## Extension ambiguity

The `.idx` incident exposed a real tension: some extensions serve double duty.

| Extension | Video context | Non-video context |
|---|---|---|
| `.idx` | VobSub subtitle index | Git pack index, database index |
| `.sub` | VobSub subtitle | Subversion metadata |
| `.xml` | NFO-style metadata | Build config, Maven POM, anything |
| `.ts` | MPEG transport stream | TypeScript source |

The directory scoping fix (layer 3) is the primary defense here -- if tapes
never enters `.git/objects/`, it never encounters `pack-*.idx`. But for
remaining ambiguity at the companion level, a category should only match files
in plausible proximity to the video. The flat-vs-recursive scoping rule
accomplishes this without needing per-extension heuristics.

One improvement worth considering: for `.xml` specifically, the NFO category
pattern `*.xml` is far too broad. It should be narrowed to known NFO filenames
(`movie.xml`, `tvshow.xml`, `episode.xml`) or dropped entirely in favor of
`*.nfo` only. If an `.xml` file contains a TMDB ID, the NFO scanner (step 2 in
the identification pipeline) already handles it regardless of companion
classification.

---

## Proposed defaults

### Scanner exclusion (hardcoded, not configurable)

```python
SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg",
    ".DS_Store", ".Spotlight-V100", ".fseventsd", ".Trashes",
    "__pycache__", ".mypy_cache", ".tox", ".pytest_cache",
    "node_modules", ".venv", "venv", ".env",
    "@eaDir",          # Synology thumbnail cache
    "#recycle",        # Synology recycle bin
    "$RECYCLE.BIN",    # Windows recycle bin
    "System Volume Information",
})
```

The principle: if a directory name unambiguously indicates non-media content, skip it.
This list is not configurable because there is no scenario where someone stores
video media inside `__pycache__` or `.git`. Making it configurable adds
complexity for a case that does not exist.

### Scanner exclusion (configurable)

```toml
[import]
exclude = []                 # user-defined glob patterns
skip_library = true          # skip library dirs during scan
```

### Companion scoping

No configuration needed. The flat-vs-recursive decision is determined by
whether the video is in a subfolder of the import root. This matches user
intent without requiring them to think about it.

### VIDEO_EXTENSIONS (single canonical set)

```python
VIDEO_EXTENSIONS = frozenset({
    ".mkv", ".mp4", ".avi", ".mov", ".m4v",
    ".ts", ".m2ts",
    ".wmv", ".flv", ".webm",
})
```

Shared between scanner and companion classifier.

---

## What this does NOT address

- **Symlink loops.** `rglob` follows symlinks by default. A symlink cycle would
  cause infinite recursion. Python 3.12+ `Path.walk()` handles this; for 3.11
  we may need to track visited inodes or set a depth limit.

- **Permissions.** The scanner does not handle `PermissionError` gracefully. A
  single unreadable directory kills the scan. Should catch and log.

- **Network mounts with high latency.** `rglob` on a slow NFS/SMB mount can
  take minutes. No timeout or progress indication exists.

- **Concurrent imports.** Two `tapes import` processes running simultaneously
  can race on file operations. Not in scope for M4 but worth noting.

---

## Summary of current bugs found

| Bug | Severity | Status |
|---|---|---|
| Scanner enters hidden directories (`.git`) | High | Fixed (ad-hoc) |
| Companion classifier scans unbounded recursively | High | Fixed (import_root scoping) |
| No same-file detection in `_execute_file_op` | Medium | Fixed (resolve + compare) |
| VIDEO_EXTENSIONS mismatch between scanner and classifier | Low | Open |
| `*.xml` companion pattern too broad | Low | Open |
| No library-overlap guard | Medium | Open |
| Scanner has no hardcoded skip list | Medium | Open |
| PermissionError not caught in scanner | Low | Open |
