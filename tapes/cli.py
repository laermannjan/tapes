"""Tapes CLI -- typer application."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from tapes.config import load_config

app = typer.Typer(name="tapes")
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
        "conflict_resolution": ("library", "conflict_resolution"),
        "language": ("metadata", "language"),
        "ignore_patterns": ("scan", "ignore_patterns"),
        "video_extensions": ("scan", "video_extensions"),
        "max_workers": ("advanced", "max_workers"),
        "tmdb_timeout": ("advanced", "tmdb_timeout"),
        "tmdb_retries": ("advanced", "tmdb_retries"),
        "auto_commit_delay": ("mode", "auto_commit_delay"),
    }

    overrides: dict[str, Any] = {}
    for key, (section, field) in mapping.items():
        if kwargs.get(key) is not None:
            overrides.setdefault(section, {})[field] = kwargs[key]

    if kwargs.get("dry_run"):
        overrides["dry_run"] = True

    if kwargs.get("delete_rejected"):
        overrides.setdefault("library", {})["delete_rejected"] = True

    if kwargs.get("auto_commit"):
        overrides.setdefault("mode", {})["auto_commit"] = True

    return overrides


def _parse_csv(value: str | None) -> list[str] | None:
    """Parse a comma-separated string into a list, or return None."""
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


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


# ---------------------------------------------------------------------------
# Single command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    path: Path | None = typer.Argument(None, help="Directory or file to process"),
    # Global
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, no file operations ever"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    # Serve
    serve: bool = typer.Option(False, "--serve", help="Serve TUI in browser", rich_help_panel="Serve"),
    serve_host: str = typer.Option(
        "0.0.0.0",  # noqa: S104
        "--serve-host",
        help="Bind address for web server",
        rich_help_panel="Serve",
    ),
    serve_port: int = typer.Option(8080, "--serve-port", help="Port for web server", rich_help_panel="Serve"),
    # Mode
    auto_commit: bool = typer.Option(False, "--auto-commit", help="Auto-process staged files", rich_help_panel="Mode"),
    auto_commit_delay: float | None = typer.Option(
        None, "--auto-commit-delay", help="Debounce delay in seconds", rich_help_panel="Mode"
    ),
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
    conflict_resolution: str | None = typer.Option(
        None, "--conflict-resolution", help="Conflict handling: auto, skip, keep_all", rich_help_panel="Library"
    ),
    delete_rejected: bool = typer.Option(
        False, "--delete-rejected", help="Delete source files of rejected items on commit", rich_help_panel="Library"
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
    """Tapes - organise your movie and TV show files."""
    import logging
    import os

    if verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("tapes").setLevel(logging.DEBUG)

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
        conflict_resolution=conflict_resolution,
        delete_rejected=delete_rejected,
        language=language,
        ignore_patterns=_parse_csv(ignore_patterns),
        video_extensions=_parse_csv(video_extensions),
        max_workers=max_workers,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=tmdb_retries,
        auto_commit=auto_commit,
        auto_commit_delay=auto_commit_delay,
    )

    cfg = load_config(config_path=config_file, cli_overrides=overrides)

    # Serve mode: CLI flag or config/env var
    if serve or cfg.mode.serve:
        os.environ.pop("TAPES_MODE__SERVE", None)
        actual_host = serve_host if serve else cfg.mode.serve_host
        actual_port = serve_port if serve else cfg.mode.serve_port
        cmd = _build_serve_command(sys.argv)
        console.print(f"Serving tapes on http://{actual_host}:{actual_port}")
        _start_server(cmd, actual_host, actual_port)
        return

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
    tui = TreeApp(
        model=model,
        movie_template=cfg.library.movie_template,
        tv_template=cfg.library.tv_template,
        root_path=root_path,
        auto_pipeline=True,
        config=cfg,
    )
    tui.run()
