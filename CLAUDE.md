# CLAUDE.md

Developer and agent guide for the `tapes` codebase.

---

## Project

Tapes is a one-shot CLI tool for organising movie and TV show files. Point it
at a directory, it identifies files by filename (guessit) and TMDB metadata,
lets you curate results in an interactive TUI, then copies/moves/links them
into a library. No database, no persistent state between runs.

GitHub: https://github.com/laermannjan/tapes

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

```
User flow:  scan -> identify -> curate (TUI) -> process

CLI
  tapes/cli.py              -- typer app, `tapes import` is the main command

TUI (textual, lazygit-inspired)
  tapes/ui/tree_app.py      -- main Textual App with keybindings
  tapes/ui/tree_view.py     -- file tree widget with cursor, staging, filtering
  tapes/ui/tree_model.py    -- FileNode, FolderNode, TreeModel, Source, UndoManager
  tapes/ui/tree_render.py   -- pure rendering (compute_dest, flatten, render_row, select_template)
  tapes/ui/detail_view.py   -- detail view for metadata curation
  tapes/ui/detail_render.py -- detail view rendering (header, grid, field display)
  tapes/ui/pipeline.py      -- auto-pipeline (guessit + two-stage TMDB per file)

Core
  tapes/scanner.py          -- find all files (with ignore_patterns filtering)
  tapes/metadata.py         -- guessit wrapper, FileMetadata, field normalization
  tapes/tmdb.py             -- TMDB API client (search_multi, get_movie, get_show, get_season_episodes)
  tapes/similarity.py       -- confidence scoring (title similarity, episode matching)
  tapes/file_ops.py         -- file processing (copy, move/copy-verify-delete, symlink)
  tapes/config.py           -- Pydantic v2 config (scan, metadata, library, dry_run)
```

---

## Design documents

**Current and authoritative:**
- `docs/plans/2026-03-06-tui-redesign.md` -- UI/UX design spec (the source of truth)
- `docs/plans/2026-03-06-tui-redesign-milestones.md` -- implementation milestones
- `docs/plans/2026-03-07-tui-visual-design.md` -- visual design spec (colors, layout, rendering)
- `docs/plans/2026-03-08-visual-fixes-remaining.md` -- **active** remaining visual issues and handoff notes

**Mockups and references:**
- `docs/mockups/color-swatches.html` -- color palette reference (all Claude palettes)
- `docs/mockups/screenshots/column-layout-mockup.html` -- before/after layout comparison
- `docs/mockups/screenshots/` -- terminal screenshots (gitignored)

**Legacy (DO NOT use for implementation):**
- `docs/legacy/` -- old designs from the initial spike and earlier iterations.
  These describe dropped features (6-tier system, SQLite, plugins, event bus,
  library management, grid TUI, companion-centric pipeline). Kept for
  historical reference only.

---

## Key decisions

- **One-shot tool.** No database, no session tracking, no persistent state.
  Each `tapes import` run is independent.
- **Every file is first-class.** No special "companion" concept in the TUI.
  Subtitles, artwork, etc. are just files with their own metadata.
- **Source-based metadata curation.** Each file has a `result` dict (used for
  destination) and a list of `Source` objects (guessit, TMDB matches). Users
  cherry-pick values from sources into the result.
- **guessit-driven.** Metadata extraction relies on guessit.
- **TMDB bearer token.** v4 read access token (`Authorization: Bearer`).
  Config field: `tmdb_token`, env var: `TMDB_TOKEN`.
- **Two templates.** `movie_template` and `tv_template`, selected by
  `media_type` field. User can edit `media_type` to switch templates.
- **Move = copy-verify-delete.** SHA-256 checksum. Operation configurable
  (copy/move/link).
- **`--dry-run`** is a global safeguard: no files are ever copied, moved,
  or modified.

---

## Conventions

- **Package manager:** `uv`. Run commands as `uv run pytest`, `uv run tapes`.
- **Commits:** short imperative subject, body with bullet points. No co-author
  lines. No em-dashes. All commits must be attributed to the repo's configured
  git user (`git config user.name` / `git config user.email`), never to Claude
  or any AI. When spawning subagents, pass `--author="$(git config user.name) <$(git config user.email)>"` explicitly.
- **Tests:** pytest in `tests/`. Mirror the source tree. Use `tmp_path` fixture
  for file system tests. Mock external HTTP with `respx` (for httpx).
- **Config:** Pydantic v2 models with sane defaults.
- **guessit field names:** `extract_metadata` normalizes guessit keys:
  `video_codec` -> `codec`, `source` -> `media_source`, `audio_codec` -> `audio`.

---

## Current status

**Pre-alpha. TUI + core pipeline complete (470 tests passing).**

Implemented: TUI (M1-M16), real TMDB integration (two-stage search),
similarity/confidence scoring, template selection, broadened scanner,
file processing on commit, config wiring, visual design overhaul.

Active work: visual polish iteration (see `docs/plans/2026-03-08-visual-fixes-remaining.md`).
Remaining: revisit similarity scoring, end-to-end manual testing, error handling.
