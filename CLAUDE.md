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
  tapes/config.py           -- Pydantic v2 config (scan, metadata, library, dry_run)
```

---

## Design documents

**Current and authoritative:**
- `docs/plans/2026-03-06-tui-redesign.md` -- UI/UX design spec (the source of truth)
- `docs/plans/2026-03-06-tui-redesign-milestones.md` -- implementation milestones (M1-M16, all complete)
- `docs/plans/2026-03-07-tui-visual-design.md` -- visual design spec (colors, layout, rendering)
- `docs/plans/2026-03-08-visual-fixes-remaining.md` -- visual fixes summary (completed)

**Completed implementation plans:**
- `docs/plans/2026-03-08-layout-overhaul.md` -- layout overhaul (separators, BottomBar, inline views)
- `docs/plans/2026-03-08-visual-and-commit-fixes.md` -- visual fixes + inline CommitView
- `docs/plans/2026-03-08-code-review-fixes.md` -- confirm/discard model, keybinding overhaul

**Testing and issue tracking:**
- `docs/testing.md` -- testing strategy (unit vs integration vs snapshot, anti-patterns)
- `docs/issues.md` -- issue tracker with triage, merges, dependencies, priority tiers

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
- **Candidate-based metadata curation.** Each file has a `metadata` dict (used
  for destination) and a list of `Candidate` objects (guessit, TMDB matches).
  Users cherry-pick values from candidates into the metadata.
- **guessit-driven.** Metadata extraction relies on guessit.
- **TMDB bearer token.** v4 read access token (`Authorization: Bearer`).
  Config field: `tmdb_token`, env var: `TMDB_TOKEN`.
- **Two templates.** `movie_template` and `tv_template`, selected by
  `media_type` field. User can edit `media_type` to switch templates.
- **Move = copy-then-delete.** Same-device move uses atomic `rename()`;
  cross-device falls back to `shutil.copy2` + `unlink`. No application-level
  checksumming -- `shutil.copy2` uses kernel-optimised copying
  (`copy_file_range`, `sendfile`) which is reliable and fast. SHA-256
  verification was evaluated and dropped due to unacceptable latency on
  large files. Operation configurable (copy/move/link/hardlink).
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
  See `docs/testing.md` for testing strategy (what to test at each level,
  anti-patterns, when to use snapshot tests).
- **Config:** Pydantic v2 models with sane defaults.
- **guessit field names:** `extract_metadata` normalizes guessit keys:
  `video_codec` -> `codec`, `source` -> `media_source`, `audio_codec` -> `audio`.

---

## Current status

**Pre-alpha. TUI + core pipeline complete.**

Implemented: TUI (M1-M16), real TMDB integration (two-stage search),
similarity scoring, template selection, broadened scanner,
file processing on commit, config wiring. Visual design overhaul
complete: Claude Code-inspired layout with horizontal separators,
inline views (metadata, commit, help), persistent bottom bar, scroll
indicators, confirm/discard editing model, double ctrl+c quit.

No modals remain. All views are inline widgets toggled via display CSS.
MetadataView edits use snapshot/restore on discard.

Next up: end-to-end manual testing, error handling.
