# CLAUDE.md

Developer and agent guide for the `tapes` codebase.

---

## Project

Tapes is a CLI tool for organising movie and TV show files -- like beets but for
video. It identifies files by filename and TMDB metadata, renames/moves them
into a library.

GitHub: https://github.com/laermannjan/tapes

**This is a rewrite** based on learnings from an initial spike. The full spec
is at `docs/plans/2026-03-05-v2-rewrite.md`.

---

## Setup

```sh
uv sync               # install deps
uv run pytest         # run all tests
uv run tapes --help   # verify CLI works
```

Requires Python 3.11+. Package manager is `uv`. Never use `pip` directly.
Dependencies must always be pinned.

---

## Architecture

The core loop is **scan -> identify -> organize**. Everything else is bonus.

```
Pipeline (4 passes)
  1. Scan         -- find video files (rglob, extension whitelist)
  2. Extract      -- guessit metadata per file (title, year, season, episode, etc.)
  3. Companions   -- stem prefix matching for subtitles, artwork, metadata files
  4. Group        -- merge criteria (season, multi-part, future: ID-based)

Models
  tapes/models.py         -- ImportGroup, FileEntry, FileMetadata, GroupType, etc.

Core modules
  tapes/scanner.py        -- scan for video files
  tapes/metadata.py       -- guessit wrapper, field normalization
  tapes/companions.py     -- stem prefix matching, whitelists, depth-limited search
  tapes/grouper.py        -- merge criteria, iterative merging, type assignment
  tapes/config.py         -- Pydantic v2 config models, sane defaults

CLI
  tapes/cli.py            -- typer app, tapes import command

TUI (textual)
  tapes/ui/app.py         -- ReviewApp (vertical accordion)
  tapes/ui/               -- widgets, modals, styles

Later tiers (not yet implemented)
  tapes/tmdb.py           -- TMDB search, get_by_id
  tapes/templates.py      -- {field} rendering
  tapes/file_ops.py       -- copy-verify-delete
```

### What changed from the initial spike

- **Dropped** SQLite, event bus, plugins, session tracking. Reintroduced if needed.
- **guessit does the heavy lifting.** No custom structural matching.
- **Bottom-up grouping.** Files -> metadata -> group by merge criteria.
- **textual TUI** replaces raw termios/ANSI.
- **Pydantic v2** for config validation with sane defaults.
- **`--dry-run`** is a global safeguard: no files are ever copied, moved, or modified.
- **`tapes import`** is the user-facing command. `tapes scan` is internal.

---

## Feature Tiers

1. **Tier 1 -- The Feel**: scan, guessit, companions, grouping, TUI. No network, no file ops.
2. **Tier 2 -- Matching**: TMDB search, confidence scoring, accept/skip/search/manual.
3. **Tier 3 -- Organize**: template rendering, copy-verify-delete, import log.
4. **Tier 4 -- Enrichment**: NFO/XML parsing, embedded tags, ID-based merge.
5. **Tier 5 -- Persistence**: cache, session restore, import history.
6. **Tier 6 -- Library management**: query, check, move, modify, stats.

---

## Key decisions

- **guessit-driven.** Metadata extraction relies on guessit. NFO/embedded tags deferred to Tier 4.
- **Merge criteria for grouping.** `MergeCriterion = Callable[[ImportGroup, ImportGroup], bool]`.
  Built-in: season merge, multi-part merge. Future: ID-based merge.
- **GroupType is structural.** `STANDALONE`, `MULTI_PART`, `SEASON`. The `media_type` field
  (`"movie"` / `"episode"` from guessit) carries the content distinction.
- **Companion discovery.** Stem prefix matching with separator (`.`, `_`, `-`).
  Directory-level companions (poster.jpg, etc.) attach to first group in that dir.
- **TMDB bearer token.** v4 read access token (`Authorization: Bearer`).
  Config field: `tmdb_token`, env var: `TMDB_TOKEN`.
- **Move = copy-verify-delete.** SHA-256 checksum. Never rename across filesystems.
- **E2E tests are primary.** TUI exposes `get_state()`/`get_history()` for testability.
- **uv for package management.** Use `[dependency-groups]` not `[project.optional-dependencies]`.

---

## Conventions

- **Package manager:** `uv`. Run commands as `uv run pytest`, `uv run tapes`.
- **Commits:** short imperative subject, body with bullet points. No co-author
  lines. No em-dashes. All commits must be attributed to the repo's configured
  git user (`git config user.name` / `git config user.email`), never to Claude
  or any AI. When spawning subagents, pass `--author="$(git config user.name) <$(git config user.email)>"` explicitly.
- **Tests:** pytest in `tests/`. Mirror the source tree. Use `tmp_path` fixture
  for file system tests. Mock external HTTP with the `responses` library.
- **Config:** Pydantic v2 models with sane defaults. Lots of things configurable.
- **guessit field names:** `parse_filename` normalizes guessit keys:
  `video_codec` -> `codec`, `source` -> `media_source`, `audio_codec` -> `audio`.

---

## Current status

**Pre-alpha rewrite -- Tier 1 in progress.**

Design spec: `docs/plans/2026-03-05-v2-rewrite.md`.
