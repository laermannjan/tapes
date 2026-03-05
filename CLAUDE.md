# CLAUDE.md

Developer and agent guide for the `tapes` codebase.

---

## Project

Tapes is a CLI tool for organising movie and TV show files — like beets but for
video. It identifies files by filename and TMDB metadata, renames/moves them
into a library, and keeps a queryable SQLite database.

GitHub: https://github.com/laermannjan/tapes

---

## Setup

```sh
uv sync               # install deps
uv run pytest         # run all tests (89 passing as of this writing)
uv run tapes --help   # verify CLI works
```

Requires Python 3.11+. Package manager is `uv`. Never use `pip` directly.

---

## Architecture

```
CLI (typer + rich)
  tapes/cli/main.py         -- app, command registration
  tapes/cli/commands/       -- one file per command

Services
  tapes/importer/service.py -- ImportService: orchestrates import pipeline
  tapes/validation.py       -- startup config validation

Core
  tapes/config/schema.py    -- Pydantic v2 config models
  tapes/config/loader.py    -- TOML loader (searches cwd, ~/.config/tapes/)
  tapes/db/schema.py        -- init_db, migration runner
  tapes/db/repository.py    -- Repository (items, sessions, operations)
  tapes/events/bus.py       -- EventBus (emit/on, per-listener exception isolation)

Identification pipeline  (tapes/identification/pipeline.py)
  1. DB cache (path + mtime + size)
  2. NFO scan (tapes/identification/nfo_scanner.py)
  3. guessit (tapes/identification/filename.py)
  4. multi-episode guard -- routes to interactive, not auto
  5. OSDB hash (tapes/identification/osdb_hash.py) -- computed but API deferred
  6. MediaInfo (tapes/identification/mediainfo.py) -- degrades gracefully
  7. TMDB search (tapes/metadata/tmdb.py)
  -> auto-accept if confidence >= threshold, else requires_interaction=True

Adapters
  tapes/metadata/base.py    -- MetadataSource ABC, SearchResult dataclass
  tapes/metadata/tmdb.py    -- TMDBSource (search, get_by_id, is_available)

Importer
  tapes/importer/file_ops.py  -- copy_verify (SHA-256), move_file, safe_rename
  tapes/importer/session.py   -- ImportSession (create/complete/abort + operations)
  tapes/importer/service.py   -- ImportService.import_path

Discovery
  tapes/discovery/scanner.py  -- recursive rglob for video files, sample exclusion
  tapes/discovery/grouper.py  -- group files by parent directory

Templates
  tapes/templates/engine.py   -- {field}, {field:02d}, {field: prefix$suffix}
                                  replace table applied to field values, not path seps
```

---

## Key decisions

See `docs/decisions/` for full ADRs. Summary:

- **No xattr.** Identification cache is path + mtime + size in SQLite.
- **Move = copy-verify-delete.** Never rename across filesystems without checksum.
- **No interactive undo.** Operations log is append-only; recovery is manual.
- **Multi-episode files are manual only.** Auto mode skips them.
- **OpenSubtitles deferred.** OSDB hash is computed but no API calls yet.
- **TMDB bearer token.** Uses v4 read access token (`Authorization: Bearer`),
  not v3 API key. Config field: `tmdb_token`, env var: `TMDB_TOKEN`.
- **Continuous confidence scoring.** Jaro-Winkler title similarity * year
  decay factor. No fixed tiers. Year is not passed as a TMDB API filter.
- **uv for package management.** Use `[dependency-groups]` not `[project.optional-dependencies]`.

---

## Conventions

- **Package manager:** `uv`. Run commands as `uv run pytest`, `uv run tapes`.
- **Commits:** short imperative subject, body with bullet points. No co-author
  lines. No em-dashes.
- **Tests:** pytest in `tests/`. Mirror the source tree. Use `tmp_path` fixture
  for file system tests. Mock external HTTP with the `responses` library.
- **Config:** Pydantic v2 models. The `import` key in TOML is renamed to
  `import_` by the loader to avoid the Python keyword.
- **guessit field names:** `screen_size` (not `resolution`), `video_codec`
  (not `codec`).

---

## Current status

**Beta.** All commands functional. 296 tests passing.
M3 milestone complete. Next: **M4 (Release)** -- CI/CD, PyPI publish, README polish.

### Milestones

**M1 — Pre-alpha (done).** `tapes import --dry-run` runs the full pipeline and
prints a summary. `tapes import` copies/moves files with SHA-256 verification
and records every operation in the DB.

**M2 — Alpha (done).** Core operations work without data loss risk:
- Task 13: pre-flight collision detection
- Task 21: query service with mini query language
- Task 22: `tapes check` for library integrity
- Task 23: `tapes move` to re-apply templates
- Task 27: check, move, log commands wired

**M3 — Beta.** All commands functional, interactive mode for low-confidence
matches. Target tasks:
- Task 11: companion file handling (subtitles, artwork, NFO)
- Task 15: plugin loader (entry points)
- Task 18: interactive disambiguation UI
- Task 25: wire query, stats, info, fields
- Task 26: wire modify command
- Task 28: NFO sidecar plugin

**M4 — Release.** CI/CD, PyPI publish, README polish.

### Task completion

| Task | Description | Status |
|------|-------------|--------|
| 1  | Project setup | done |
| 2  | CLI skeleton | done |
| 3  | Config schema and loading | done |
| 4  | SQLite schema and repository | done |
| 5  | Filename parsing | done |
| 6  | OpenSubtitles hash | done |
| 7  | MediaInfo wrapper | done |
| 8  | TMDB metadata source | done |
| 9  | Identification pipeline | done |
| 10 | Template rendering and filename sanitization | done |
| 11 | Companion file classification and renaming | done |
| 12 | File scanner and grouper | done |
| 13 | Pre-flight collision detector | done |
| 14 | EventBus | done |
| 15 | Plugin loader | done |
| 16 | File operations | done |
| 17 | Session tracking | done |
| 18 | Rich-based interactive import display | done |
| 19 | Import service | done |
| 20 | Startup validation | done |
| 21 | Query service | done |
| 22 | tapes check command | done |
| 23 | tapes move command | done |
| 24 | Wire import command | done |
| 25 | Wire query, stats, info, fields commands | done |
| 26 | Wire modify command | done |
| 27 | Wire move, check, log commands | done |
| 28 | NFO sidecar plugin | done |

Full task specs: `docs/plans/2026-03-04-tapes-implementation.md`.
Design spec: `docs/plans/2026-03-04-tapes-design.md`.

---

## Running a real test

```sh
# Set up a minimal config
cat > tapes.toml <<EOF
[library]
movies = "/tmp/tapes-movies"

[metadata]
tmdb_token = "your-token-here"
EOF

# Create test input
mkdir -p /tmp/downloads
cp some_movie.mkv /tmp/downloads/

# Preview
tapes import /tmp/downloads --dry-run

# Actually import
tapes import /tmp/downloads
```
