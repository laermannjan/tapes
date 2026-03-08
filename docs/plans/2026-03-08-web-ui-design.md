# Web UI Design

## Goal

Serve tapes in a Docker container accessible via browser, so it can run on
a self-hosted server alongside Plex/Jellyfin.

## Approach

Use `textual-serve` to serve the existing Textual TUI over WebSocket. Each
browser connection gets its own app instance. The existing TUI code is reused
unchanged. A thin `tapes serve` command wires config, scanning, and
textual-serve together.

## Architecture

```
Browser --WebSocket--> textual-serve --> TreeApp (per connection)
                                            |-- scanner
                                            |-- pipeline (guessit + TMDB)
                                            |-- tree_model
                                            |-- file_ops (on commit)
```

The Docker container runs `tapes serve`. Configuration comes from environment
variables and/or a mounted config file (existing config system, no changes).

## New config

`ScanConfig.import_path: str = ""` -- default directory to scan. Settable via
`TAPES_SCAN__IMPORT_PATH` env var, config file, or `--import-path` CLI flag.

## New CLI command: `tapes serve`

Flags:
- `--host` (default `0.0.0.0`)
- `--port` (default `8080`)
- `--import-path` (required if not in config)
- All existing config flags (--tmdb-token, --operation, etc.)

Each connection: load config, scan import_path, build TreeModel, run guessit,
create TreeApp, hand to textual-serve. TMDB worker starts in background as
usual.

## Removed: `tapes tree`

Dev/debug command, superseded by `tapes serve`.

## Docker

**Dockerfile:** `python:3.13-slim`, install uv, copy project, `uv sync`,
expose 8080, `CMD ["uv", "run", "tapes", "serve"]`.

**docker-compose.yaml:**

```yaml
services:
  tapes:
    build: .
    ports:
      - "8080:8080"
    environment:
      - TAPES_SCAN__IMPORT_PATH=/import
      - TAPES_METADATA__TMDB_TOKEN=your-token-here
      - TAPES_LIBRARY__MOVIES=/library/movies
      - TAPES_LIBRARY__TV=/library/tv
    volumes:
      - /path/to/downloads:/import
      - /path/to/library:/library
```

Users mount download directory as import source, library directory as output.
Optional config file mount at `/config/config.yaml`.

## Dependencies

Add `textual-serve` to `pyproject.toml`.

## Existing code changes

Minimal. TreeApp stays unchanged -- the serve command builds TreeModel and
passes it in, same pattern as `import_cmd`. The only difference is wrapping
in textual-serve instead of calling `app.run()`.

## Constraints

- Terminal aesthetic in browser (acceptable per design decision)
- Keyboard shortcuts may conflict with browser shortcuts
- No mobile responsiveness
- No REST API (can add later if needed)

## Non-goals

- Multiple simultaneous sessions sharing state
- Network storage (NFS/SMB) handling in container
- Custom web frontend
- REST/WebSocket API for third-party integrations
