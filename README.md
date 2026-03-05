# tapes

A command-line tool for organising movie and TV show files. It identifies media
files by filename, fetches metadata from TMDB, renames and moves them into a
clean directory structure, and maintains a queryable local library.

Modelled after [beets](https://beets.io) but for video.

**Status: pre-alpha.** `tapes import --dry-run` works end to end. Most other
commands are stubbed. See [What works](#what-works).

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for package management
- A [TMDB read access token](https://www.themoviedb.org/settings/api) (free)

## Setup

```sh
git clone https://github.com/laermannjan/tapes
cd tapes
uv sync
```

Copy and edit the example config:

```sh
cp tapes.toml.example tapes.toml
```

Minimal `tapes.toml`:

```toml
[library]
movies = "~/Media/Movies"
tv     = "~/Media/TV"

[metadata]
tmdb_token = "your-token-here"
```

Or export the token as an environment variable:

```sh
export TMDB_TOKEN=your-token-here
```

## Usage

Preview what would be imported without touching any files:

```sh
tapes import /path/to/downloads --dry-run
```

Import files (default mode: copy):

```sh
tapes import /path/to/downloads
```

Override mode for a single run:

```sh
tapes import /path/to/downloads --mode move
```

Run tests:

```sh
uv run pytest
```

## What works

- `tapes import --dry-run` — full pipeline: scan, identify (guessit + TMDB),
  render destination paths, print summary table
- `tapes import` — copy/move/link/hardlink with SHA-256 verification
- Identification pipeline: DB cache, NFO scan, guessit, MediaInfo, TMDB
- Session and operation logging to SQLite

## What is stubbed / not yet implemented

- `tapes move` — move already-imported files to a new path
- `tapes check` — verify files still exist at their recorded paths
- `tapes modify` — manually update metadata and rename on disk
- `tapes query` — search the library
- `tapes info / fields / stats / log` — library introspection commands
- Interactive mode (disambiguation when confidence is low)
- Companion file handling (subtitles, artwork, NFO)
- Pre-flight collision detection
- Plugin system

See [docs/plans/2026-03-04-tapes-implementation.md](docs/plans/2026-03-04-tapes-implementation.md)
for the full task list.

## Configuration

All options with defaults:

```toml
[library]
movies  = ""                                 # required
tv      = ""                                 # required
db_path = "~/.local/share/tapes/library.db"

[import]
mode                 = "copy"   # copy | move | link | hardlink
confidence_threshold = 0.9
dry_run              = false

[metadata]
tmdb_token   = ""               # or set TMDB_TOKEN env var

[templates]
movie = "{title} ({year})/{title} ({year}){ext}"
tv    = "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d} - {episode_title}{ext}"

[replace]
": " = " - "
"/"  = "-"
```

## License

MIT
