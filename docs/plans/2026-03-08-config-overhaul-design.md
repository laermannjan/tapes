# Config Overhaul Design (I29)

Date: 2026-03-08

## Goal

Migrate config from plain Pydantic BaseModel to pydantic-settings. Every
setting is available at all three layers (CLI flag, env var, config file) with
clear precedence. Settings are split into first-class (stable, documented) and
advanced (exposed but no stability guarantee).

## Layers and precedence

    CLI flags > env vars > YAML config file > defaults

## Config model

Migrate `TapesConfig` from `BaseModel` to pydantic-settings `BaseSettings`.
Keep the current nested structure, add new groups and fields.

```
TapesConfig (BaseSettings)
  env_prefix = "TAPES_"
  env_nested_delimiter = "__"

  scan: ScanConfig
    ignore_patterns: list[str]           # existing
    video_extensions: list[str]          # new, from scanner.py VIDEO_EXTENSIONS

  metadata: MetadataConfig
    tmdb_token: str                      # existing
    auto_accept_threshold: float         # existing
    margin_accept_threshold: float       # new, from similarity.py
    min_accept_margin: float             # new, from similarity.py
    max_results: int                     # new, from tmdb.py MAX_TMDB_RESULTS

  library: LibraryConfig
    movies: str                          # existing
    tv: str                              # existing
    movie_template: str                  # existing
    tv_template: str                     # existing
    operation: Literal[...]              # existing, add validation

  advanced: AdvancedConfig               # new group
    max_workers: int                     # from pipeline.py DEFAULT_MAX_WORKERS
    tmdb_timeout: float                  # from tmdb.py REQUEST_TIMEOUT_S
    tmdb_retries: int                    # from tmdb.py retry stop_after_attempt

  dry_run: bool                          # existing
```

### Operation validation

Change `operation: str = "copy"` to
`operation: Literal["copy", "move", "link", "hardlink"] = "copy"`.

## Config file

YAML format (matches self-hosted community conventions, natural lists/nesting).
Loaded via pydantic-settings `YamlConfigSettingsSource`.

Default location: `$XDG_CONFIG_HOME/tapes/config.yaml` (typically
`~/.config/tapes/config.yaml`). Overridable via `TAPES_CONFIG` env var and
`--config` CLI flag.

Example config file:

```yaml
library:
  movies: /media/movies
  tv: /media/tv
  movie_template: "{title} ({year})/{title} ({year}).{ext}"
  tv_template: "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
  operation: copy

metadata:
  tmdb_token: eyJ...
  auto_accept_threshold: 0.85
  margin_accept_threshold: 0.6
  min_accept_margin: 0.15
  max_results: 3

scan:
  ignore_patterns: [Thumbs.db, .DS_Store, desktop.ini]
  video_extensions: [.mkv, .mp4, .avi, .mov, .m4v, .ts, .m2ts, .wmv, .flv]

advanced:
  max_workers: 4
  tmdb_timeout: 10
  tmdb_retries: 3
```

## Env vars

Double underscore delimiter for nesting. `TAPES_` prefix.

Examples:
- `TAPES_DRY_RUN=1`
- `TAPES_LIBRARY__OPERATION=move`
- `TAPES_LIBRARY__MOVIES=/media/movies`
- `TAPES_METADATA__TMDB_TOKEN=xxx`
- `TAPES_ADVANCED__MAX_WORKERS=8`

Drop the manual `TMDB_TOKEN` env var handling in `model_post_init` --
pydantic-settings handles env loading automatically. The env var name becomes
`TAPES_METADATA__TMDB_TOKEN`. For backwards compat, keep `TMDB_TOKEN` as a
validation alias so both work.

## CLI flags

Flat flags on typer commands, grouped in `--help` output via `rich_help_panel`.

```
Library:
  --library-movies PATH
  --library-tv PATH
  --movie-template TEXT
  --tv-template TEXT
  --operation [copy|move|link|hardlink]

Metadata:
  --tmdb-token TEXT
  --auto-accept-threshold FLOAT
  --margin-accept-threshold FLOAT
  --min-accept-margin FLOAT
  --max-results INT

Scan:
  --ignore-patterns TEXT  (comma-separated or repeated)
  --video-extensions TEXT  (comma-separated or repeated)

Advanced:
  --max-workers INT
  --tmdb-timeout FLOAT
  --tmdb-retries INT

General:
  --config PATH
  --dry-run
  --verbose
```

Typer collects only explicitly-provided flags into a dict (using sentinel
defaults to distinguish "not provided" from "provided as default value"). That
dict is passed as `_cli_overrides` to `TapesConfig`, which injects them as the
highest-priority source via `settings_customise_sources`.

## Migration plan

### config.py
- `BaseModel` -> `BaseSettings` (from pydantic-settings)
- Add `model_config` with `env_prefix`, `env_nested_delimiter`, yaml source
- Add `AdvancedConfig` group with `max_workers`, `tmdb_timeout`, `tmdb_retries`
- Add `video_extensions` to `ScanConfig`
- Add `margin_accept_threshold`, `min_accept_margin`, `max_results` to
  `MetadataConfig`
- Change `operation: str` to `Literal["copy", "move", "link", "hardlink"]`
- Add CLI override injection via `settings_customise_sources`
- Remove manual `model_post_init` env var handling
- Add `TMDB_TOKEN` as validation alias for backwards compat
- XDG default path resolution for config file

### cli.py
- Add all flags to `import_cmd` and `tree_cmd` with `rich_help_panel` grouping
- Build override dict from explicitly-provided flags (sentinel pattern)
- Pass overrides to `TapesConfig` constructor
- Remove manual `load_config` call (settings model handles file loading)

### Consumers (read config instead of hardcoded constants)
- `scanner.py`: use `config.scan.video_extensions` instead of `VIDEO_EXTENSIONS`
- `similarity.py`: use `config.metadata.{auto_accept_threshold, margin_accept_threshold, min_accept_margin}`
- `tmdb.py`: use `config.advanced.tmdb_timeout`, `config.advanced.tmdb_retries`,
  `config.metadata.max_results`
- `pipeline.py`: use `config.advanced.max_workers`

### Dependencies
- Add `pydantic-settings[yaml]` to pyproject.toml

## What stays hardcoded

Similarity scoring weights (STRICT_WEIGHT, SHOW_TITLE_WEIGHT, etc.),
YEAR_TOLERANCE, copy buffer size (_COPY_BUFSIZE), all UI constants (SCROLLOFF,
DETAIL_CHROME_LINES, HELP_HEIGHT, quit timeout). These are implementation
details, not user-facing config. They remain as module-level constants.
