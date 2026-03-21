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
        "poll_interval": ("mode", "poll_interval"),
        "log_file": ("mode", "log_file"),
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

    if kwargs.get("headless"):
        overrides.setdefault("mode", {})["headless"] = True

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


def _print_jq_summary(log_path: Path | None) -> None:
    """Print a per-file summary from the JSON log using jq (if available)."""
    import shutil
    import subprocess

    if not log_path or not log_path.exists():
        return
    jq_bin = shutil.which("jq")
    if not jq_bin:
        return

    try:
        result = subprocess.run(  # noqa: S603
            [
                jq_bin,
                "-r",
                'select(.file) | [.file, .event, (.reason // .dest // "")] | @tsv',
            ],
            input=log_path.read_text(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            print("\n--- Summary ---", file=sys.stderr)  # noqa: T201
            print(result.stdout.strip(), file=sys.stderr)  # noqa: T201
    except (subprocess.TimeoutExpired, OSError):
        pass


def _setup_logging(*, headless: bool, verbose: bool, log_file: str | None) -> Path | None:
    """Configure structlog with JSON output. Returns the log file path (for jq summary).

    Args:
        headless: If True, also log to stderr.
        verbose: If True, set tapes logger to DEBUG. Otherwise INFO.
        log_file: Path to log file. None = default XDG location. "" = disable file logging.
    """
    import logging

    import structlog

    log_level = logging.DEBUG if verbose else logging.INFO

    # Suppress noisy third-party loggers.
    # Don't use basicConfig - it adds a default stderr handler.
    logging.getLogger().setLevel(logging.WARNING)

    # structlog processors for the structlog -> stdlib bridge
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # JSON formatter for log file (always JSON, machine-parseable)
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    tapes_logger = logging.getLogger("tapes")
    tapes_logger.setLevel(log_level)
    tapes_logger.propagate = False
    tapes_logger.handlers.clear()

    resolved_log_path: Path | None = None

    # File handler (always JSON)
    if log_file != "":
        if log_file is None:
            from platformdirs import user_state_dir

            log_dir = Path(user_state_dir("tapes"))
            log_dir.mkdir(parents=True, exist_ok=True)
            resolved_log_path = log_dir / "tapes.log"
        else:
            resolved_log_path = Path(log_file)
            resolved_log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(resolved_log_path)
        file_handler.setFormatter(json_formatter)
        tapes_logger.addHandler(file_handler)

    # Stderr handler (headless only)
    # Human-readable when stderr is a terminal, JSON when piped
    if headless:
        if sys.stderr.isatty():
            stderr_formatter = structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(),
                ],
            )
        else:
            stderr_formatter = json_formatter

        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(stderr_formatter)
        tapes_logger.addHandler(stderr_handler)

    return resolved_log_path


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
    one_shot: bool = typer.Option(
        False, "--one-shot", help="Process once and exit (implies --headless --poll-interval 0)", rich_help_panel="Mode"
    ),
    headless: bool = typer.Option(
        False, "--headless", help="Run without UI (implies --auto-commit)", rich_help_panel="Mode"
    ),
    log_file: str | None = typer.Option(
        None, "--log-file", help="Log file path (empty to disable)", rich_help_panel="Mode"
    ),
    auto_commit: bool = typer.Option(False, "--auto-commit", help="Auto-process staged files", rich_help_panel="Mode"),
    auto_commit_delay: float | None = typer.Option(
        None, "--auto-commit-delay", help="Debounce delay in seconds", rich_help_panel="Mode"
    ),
    poll_interval: float | None = typer.Option(
        None, "--poll-interval", help="Directory poll interval in seconds (0 to disable)", rich_help_panel="Mode"
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
    import os

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
        poll_interval=poll_interval,
        headless=headless,
        log_file=log_file,
    )

    cfg = load_config(config_path=config_file, cli_overrides=overrides)

    # One-shot implies headless + poll_interval=0
    if one_shot:
        cfg.mode.headless = True
        cfg.mode.poll_interval = 0.0

    # Headless implies auto_commit
    is_headless = headless or cfg.mode.headless
    if is_headless:
        cfg.mode.auto_commit = True

    # Validate: headless + serve conflict
    is_serve = serve or cfg.mode.serve
    if is_headless and is_serve:
        console.print("[red]Error:[/red] Cannot use --headless with --serve.")
        raise typer.Exit(code=1)

    # Validate: TMDB token required
    if not cfg.metadata.tmdb_token:
        console.print("[red]Error:[/red] No TMDB token configured. Set --tmdb-token or TAPES_METADATA__TMDB_TOKEN.")
        raise typer.Exit(code=1)

    # Set up logging
    resolved_log_file = log_file if log_file is not None else cfg.mode.log_file
    _log_path = _setup_logging(headless=is_headless, verbose=verbose, log_file=resolved_log_file)

    # Serve mode: CLI flag or config/env var
    if is_serve:
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
    if is_headless:
        tui.run(headless=True)
        # Show jq summary only when stderr was piped (JSON output).
        # When stderr is a terminal, the user already sees human-readable logs.
        if not sys.stderr.isatty():
            _print_jq_summary(_log_path)
    else:
        tui.run()
