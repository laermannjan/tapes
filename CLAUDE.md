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
uv sync                    # install deps
uv run pre-commit install  # enable pre-commit hooks
uv run pytest              # run all tests
uv run tapes --help        # verify CLI works
```

Requires Python 3.11+. Package manager is `uv`. Never use `pip` directly.
Dependencies must always be pinned.

### Code quality checks

Two mechanisms enforce ruff + ty on all Python changes:

**Pre-commit hooks** (`.pre-commit-config.yaml`) -- run on `git commit` on
your machine. Uses `ruff-pre-commit` (official repo, version synced from
`uv.lock` via `sync-with-uv`) for ruff, and a local `uv run ty check` hook
for ty (no official pre-commit repo yet). `pre-commit-uv` plugin ensures
pre-commit uses `uv` instead of `pip` for hook environments.

**Claude Code hook** (`.claude/settings.json`) -- runs `ruff check --fix`,
`ruff format`, and `ty check` after every Python file edit/write during Claude
Code sessions. Uses `uv tool run` instead of `uv run` because the sandbox
environment corrupts venv binaries during cross-filesystem hardlink fallback
(the Rust binaries for ruff/ty become invalid). This is a sandbox-only issue;
on a real machine `uv run` works fine. The `.claude/` directory is gitignored,
so this hook config lives only in the sandbox. If missing, create
`.claude/settings.json` with a `PostToolUse` hook on `Edit|Write` that runs
`uv tool run ruff check --fix`, `uv tool run ruff format`, and
`uv tool run ty check` on `.py` files.

---

## Pipeline

The intended behavior of the TMDB identification pipeline (search,
score, auto-accept, auto-stage) is documented in
`docs/pipeline-model.md`. That file is the authoritative reference.
Audit code against that model, not the other way around.

---

## Architecture

See `docs/vocabulary.md` for canonical terminology.

```
User flow:  scan -> identify -> curate (TUI) -> process

CLI
  tapes/cli.py              -- typer app, `tapes import` is the main command

TUI (textual, Claude Code-inspired layout)
  tapes/ui/tree_app.py      -- main Textual App (AppState enum), keybindings, inline view management
  tapes/ui/tree_view.py     -- file tree widget with cursor, staging, filtering, scroll indicators
  tapes/ui/tree_render.py   -- pure rendering (compute_dest, flatten, render_row, render_separator, full_extension)
  tapes/ui/metadata_view.py -- inline metadata curation view (confirm/discard model)
  tapes/ui/metadata_render.py -- metadata view rendering (header, grid, field display)
  tapes/ui/commit_view.py   -- inline commit confirmation view with file categorization
  tapes/ui/help_view.py     -- inline help view with workflow guide
  tapes/ui/bottom_bar.py    -- persistent bottom bar (stats, search, operation mode, hints)
  tapes/ui/colors.py        -- color palette + semantic tokens

Core
  tapes/tree_model.py       -- FileNode, FolderNode, TreeModel, Candidate
  tapes/pipeline.py         -- auto-pipeline (guessit + two-stage TMDB per file), PipelineParams dataclass
  tapes/categorize.py       -- categorize staged files for commit view
  tapes/scanner.py          -- find all files (with ignore_patterns filtering)
  tapes/extract.py          -- guessit wrapper, metadata extraction, field normalization
  tapes/templates.py        -- pure template/path utilities (no UI dependency)
  tapes/tmdb.py             -- TMDB API client (search_multi, get_movie, get_show, get_season_episodes)
  tapes/similarity.py       -- scoring (title similarity, episode matching)
  tapes/file_ops.py         -- file processing (copy, move, symlink, hardlink)
  tapes/config.py           -- Pydantic v2 config (scan, metadata, library, mode, dry_run)
  tapes/conflicts.py        -- unified conflict detection (virtual nodes, auto/skip/keep_all)
```

---

## Design documents

**Active references:**
- `docs/decisions.md` -- architectural decisions, rejected approaches, and learnings
- `docs/testing.md` -- testing strategy (unit vs integration vs snapshot, anti-patterns)
- `docs/issues.md` -- issue tracker with triage, merges, dependencies, priority tiers
- `docs/mockups/` -- color palette, layout mockups, terminal screenshots

**Historical archive (DO NOT use for implementation):**
- `docs/legacy/` -- all completed plans, old designs, and code reviews.
  Includes early-stage designs (6-tier system, SQLite, plugins, event bus,
  grid TUI, companion-centric pipeline) and all implementation plans from
  the TUI redesign through visual overhaul. Kept for historical reference.

---

## Key decisions

See `docs/decisions.md` for all architectural decisions, rejected approaches,
and learnings. Key points:

- **One-shot by default, persistent with polling.** No database, no persistent state.
- **Every file is first-class.** No companion concept.
- **Candidate-based metadata curation.** Metadata dict + candidate list.
- **guessit-driven.** Filename-based metadata extraction.
- **Two templates** selected by `media_type` field.
- **Single command, composable flags.** `--serve`, `--auto-commit`, `--headless`, `--one-shot`.
- **FileStatus enum.** PENDING/STAGED/REJECTED replaces boolean pair.
- **Unified conflict detection.** Virtual nodes, three policies (auto/skip/keep_all).
- **structlog.** JSON logging with context binding for file tracing.
- **Move = copy-then-delete.** Kernel-optimized, no checksumming.
- **`--dry-run`** safeguard: nothing happens to files.

---

## Conventions

- **Package manager:** `uv`. Run commands as `uv run pytest`, `uv run tapes`.
- **Commits:** short imperative subject, body with bullet points. No co-author
  lines. No em-dashes. All commits must be attributed to the repo's configured
  git user (`git config user.name` / `git config user.email`), never to Claude
  or any AI. When spawning subagents, pass `--author="$(git config user.name) <$(git config user.email)>"` explicitly.
- **Tests:** pytest in `tests/`. Mirror the source tree. Use `tmp_path` fixture
  for file system tests. Mock external HTTP with `respx` (for httpx).
  See `docs/testing.md` for testing strategy (what to test at each level,
  anti-patterns, when to use snapshot tests).
- **Config:** Pydantic v2 models with sane defaults.
- **guessit field names:** `extract_metadata` normalizes guessit keys:
  `video_codec` -> `codec`, `source` -> `media_source`, `audio_codec` -> `audio`.

---

## Current status

**Pre-alpha. Core features complete.**

Implemented: TUI with inline views (metadata, commit, help), real TMDB
integration (two-stage search), similarity scoring, template selection,
file processing on commit, config wiring. CLI redesign with composable
mode flags. Conflict system with FileStatus enum and unified detection.
Auto-commit with debounce. Directory polling with tree rebuild.
Headless/one-shot mode. Structured JSON logging via structlog.

Next up: Dockerfile, Unraid template, end-to-end manual testing.
