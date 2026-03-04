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

**Pre-alpha.** `tapes import --dry-run` works end to end.

### Implemented (89 tests)

- Project scaffolding, CLI skeleton (all commands stubbed)
- Config schema + loader
- SQLite schema, migrations, repository
- Filename parsing (guessit), OSDB hash, MediaInfo wrapper
- TMDB metadata source with confidence scoring
- Identification pipeline (7 steps)
- Template engine with conditional syntax and replace table
- File discovery + grouper
- EventBus
- File ops (copy_verify, move, rename)
- Import session tracking
- Import service (scan, identify, execute, DB write)
- Startup validation
- `tapes import` command wired to ImportService

### Not yet implemented (remaining plan tasks)

| Task | Description |
|------|-------------|
| 13   | Pre-flight collision detection in ImportService |
| 15   | Plugin loader (entry points) |
| 18   | Interactive disambiguation UI (rich prompts) |
| 21   | `tapes move` command |
| 22   | `tapes check` command |
| 23   | `tapes modify` command |
| 25   | `tapes query` command |
| 26   | `tapes info / fields / stats / log` commands |
| 27   | Companion file handling (subtitles, artwork, NFO) |
| 28   | CI/CD (GitHub Actions, PyPI publish) |

Full task descriptions are in `docs/plans/2026-03-04-tapes-implementation.md`.
Design spec is in `docs/plans/2026-03-04-tapes-design.md`.

---

## Running a real test

```sh
# Set up a minimal config
cat > tapes.toml <<EOF
[library]
movies = "/tmp/tapes-movies"

[metadata]
tmdb_api_key = "your-real-key"
EOF

# Create test input
mkdir -p /tmp/downloads
cp some_movie.mkv /tmp/downloads/

# Preview
tapes import /tmp/downloads --dry-run

# Actually import
tapes import /tmp/downloads
```
