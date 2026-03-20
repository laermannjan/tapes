"""Tapes CLI -- typer application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from tapes.config import load_config

app = typer.Typer(name="tapes", no_args_is_help=True, invoke_without_command=True)
console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Override builder
# ---------------------------------------------------------------------------


def _build_overrides(**kwargs: Any) -> dict[str, Any]:
    """Build a nested config override dict from flat CLI flag values.

    Only non-None values are included. The mapping translates flat CLI flag
    names to their nested config section/field paths.
    """
    mapping: dict[str, tuple[str, str]] = {
        "library_movies": ("library", "movies"),
        "library_tv": ("library", "tv"),
        "movie_template": ("library", "movie_template"),
        "tv_template": ("library", "tv_template"),
        "operation": ("library", "operation"),
        "tmdb_token": ("metadata", "tmdb_token"),
        "min_score": ("metadata", "min_score"),
        "min_prominence": ("metadata", "min_prominence"),
        "max_results": ("metadata", "max_results"),
        "duplicate_resolution": ("metadata", "duplicate_resolution"),
        "disambiguation": ("metadata", "disambiguation"),
        "language": ("metadata", "language"),
        "ignore_patterns": ("scan", "ignore_patterns"),
        "video_extensions": ("scan", "video_extensions"),
        "max_workers": ("advanced", "max_workers"),
        "tmdb_timeout": ("advanced", "tmdb_timeout"),
        "tmdb_retries": ("advanced", "tmdb_retries"),
    }

    overrides: dict[str, Any] = {}
    for key, (section, field) in mapping.items():
        if kwargs.get(key) is not None:
            overrides.setdefault(section, {})[field] = kwargs[key]

    if kwargs.get("dry_run"):
        overrides["dry_run"] = True

    return overrides


def _parse_csv(value: str | None) -> list[str] | None:
    """Parse a comma-separated string into a list, or return None."""
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """Tapes -- organise your movie and TV show files."""
    import logging

    if verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("tapes").setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("import")
def import_cmd(
    path: Path | None = typer.Argument(None, help="Directory or file to import"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, no file operations ever"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    # Library
    library_movies: Path | None = typer.Option(
        None, "--library-movies", help="Movies library directory", rich_help_panel="Library"
    ),
    library_tv: Path | None = typer.Option(
        None, "--library-tv", help="TV library directory", rich_help_panel="Library"
    ),
    movie_template: str | None = typer.Option(
        None, "--movie-template", help="Movie filename template", rich_help_panel="Library"
    ),
    tv_template: str | None = typer.Option(
        None, "--tv-template", help="TV filename template", rich_help_panel="Library"
    ),
    operation: str | None = typer.Option(
        None, "--operation", help="File operation: copy, move, link, hardlink", rich_help_panel="Library"
    ),
    # Metadata
    tmdb_token: str | None = typer.Option(
        None, "--tmdb-token", help="TMDB API bearer token", rich_help_panel="Metadata"
    ),
    min_score: float | None = typer.Option(
        None, "--min-score", help="Minimum similarity score for auto-accept", rich_help_panel="Metadata"
    ),
    min_prominence: float | None = typer.Option(
        None, "--min-prominence", help="Minimum prominence (gap to second) for auto-accept", rich_help_panel="Metadata"
    ),
    max_results: int | None = typer.Option(
        None, "--max-results", help="Max TMDB search results", rich_help_panel="Metadata"
    ),
    duplicate_resolution: str | None = typer.Option(
        None, "--duplicate-resolution", help="Duplicate handling: auto, warn, off", rich_help_panel="Metadata"
    ),
    disambiguation: str | None = typer.Option(
        None, "--disambiguation", help="Disambiguation: auto, warn, off", rich_help_panel="Metadata"
    ),
    language: str | None = typer.Option(
        None, "--language", help="TMDB language code (e.g. de, fr, en-US)", rich_help_panel="Metadata"
    ),
    # Scan
    ignore_patterns: str | None = typer.Option(
        None, "--ignore-patterns", help="Comma-separated ignore patterns", rich_help_panel="Scan"
    ),
    video_extensions: str | None = typer.Option(
        None, "--video-extensions", help="Comma-separated video extensions", rich_help_panel="Scan"
    ),
    # Advanced
    max_workers: int | None = typer.Option(
        None, "--max-workers", help="Max parallel workers", rich_help_panel="Advanced"
    ),
    tmdb_timeout: float | None = typer.Option(
        None, "--tmdb-timeout", help="TMDB request timeout (seconds)", rich_help_panel="Advanced"
    ),
    tmdb_retries: int | None = typer.Option(
        None, "--tmdb-retries", help="TMDB request retry count", rich_help_panel="Advanced"
    ),
) -> None:
    """Import video files into the library."""
    overrides = _build_overrides(
        dry_run=dry_run,
        library_movies=str(library_movies) if library_movies is not None else None,
        library_tv=str(library_tv) if library_tv is not None else None,
        movie_template=movie_template,
        tv_template=tv_template,
        operation=operation,
        tmdb_token=tmdb_token,
        min_score=min_score,
        min_prominence=min_prominence,
        max_results=max_results,
        duplicate_resolution=duplicate_resolution,
        disambiguation=disambiguation,
        language=language,
        ignore_patterns=_parse_csv(ignore_patterns),
        video_extensions=_parse_csv(video_extensions),
        max_workers=max_workers,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=tmdb_retries,
    )

    cfg = load_config(config_path=config_file, cli_overrides=overrides)

    from tapes.scanner import scan
    from tapes.tree_model import build_tree
    from tapes.ui.tree_app import TreeApp

    # Resolve path: CLI argument > config import_path
    if path is not None:
        resolved = path.resolve()
    elif cfg.scan.import_path:
        resolved = Path(cfg.scan.import_path).resolve()
    else:
        console.print("[red]Error:[/red] No path provided. Pass a directory or set scan.import_path in config.")
        raise typer.Exit(code=1)

    files = scan(resolved, ignore_patterns=cfg.scan.ignore_patterns, video_extensions=cfg.scan.video_extensions)
    if not files:
        console.print("No files found.")
        return

    root_path = resolved if resolved.is_dir() else resolved.parent
    model = build_tree(files, root_path)
    movie_tmpl = cfg.library.movie_template
    tv_tmpl = cfg.library.tv_template
    tui = TreeApp(
        model=model,
        movie_template=movie_tmpl,
        tv_template=tv_tmpl,
        root_path=root_path,
        auto_pipeline=True,
        config=cfg,
    )
    tui.run()


def _build_serve_command(argv: list[str]) -> str:
    """Build a shell command from argv, stripping --serve* flags.

    Removes --serve, --serve-host <value>, and --serve-port <value>.
    Handles both --flag value and --flag=value syntax.
    Quotes arguments that contain spaces.
    """
    import shlex

    serve_value_flags = {"--serve-host", "--serve-port"}
    result: list[str] = []
    skip_next = False

    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--serve":
            continue
        if arg in serve_value_flags:
            skip_next = True
            continue
        if any(arg.startswith(f"{flag}=") for flag in serve_value_flags):
            continue
        result.append(shlex.quote(arg))

    return " ".join(result)


def _start_server(command: str, host: str, port: int) -> None:
    """Start the textual-serve server. Extracted for testability."""
    from textual_serve.server import Server

    server = Server(command, host=host, port=port, title="tapes")
    server.serve()


@app.command("serve")
def serve_cmd(
    import_path: Path | None = typer.Option(None, "--import-path", help="Directory to import"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address"),  # noqa: S104
    port: int = typer.Option(8080, "--port", help="Port number"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Serve the tapes TUI over the browser."""
    import shlex

    cfg = load_config(config_path=config_file)

    # Resolve import path: --import-path flag > config
    resolved_path = import_path or (Path(cfg.scan.import_path) if cfg.scan.import_path else None)
    if resolved_path is None:
        console.print("[red]Error:[/red] No import path. Use --import-path or set TAPES_SCAN__IMPORT_PATH.")
        raise typer.Exit(code=1)

    if cfg.metadata.tmdb_token:
        console.print(f"TMDB token: configured ({len(cfg.metadata.tmdb_token)} chars)")
    else:
        console.print("[yellow]Warning:[/yellow] No TMDB token configured. Set TAPES_METADATA__TMDB_TOKEN.")

    cmd = f"tapes import {shlex.quote(str(resolved_path))}"
    if config_file:
        cmd += f" --config {shlex.quote(str(config_file))}"

    console.print(f"Serving tapes on http://{host}:{port}")
    _start_server(cmd, host, port)
