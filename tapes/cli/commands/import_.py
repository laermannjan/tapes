import typer
from pathlib import Path
from typing import Optional

import sqlite3
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.metadata.tmdb import TMDBSource
from tapes.validation import validate_config, ConfigError
from tapes.importer.service import ImportService

console = Console()


def command(
    path: Path = typer.Argument(..., help="Path to scan for media files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes."),
    interactive: bool = typer.Option(False, "--interactive", help="Force interactive for all groups."),
    no_db: bool = typer.Option(False, "--no-db", help="Identify and rename only, no DB writes."),
    mode: Optional[str] = typer.Option(None, "--mode", help="copy|move|link|hardlink"),
    confidence: Optional[float] = typer.Option(None, "--confidence", help="Override confidence threshold."),
):
    """Import media files from PATH."""
    cfg = load_config()

    # Apply CLI overrides
    if dry_run:
        cfg.import_.dry_run = True
    if mode:
        cfg.import_.mode = mode
    if confidence is not None:
        cfg.import_.confidence_threshold = confidence
    if interactive:
        cfg.import_.interactive = True
    if no_db:
        cfg.import_.no_db = True

    try:
        validate_config(cfg)
    except ConfigError as e:
        err_console = Console(stderr=True)
        err_console.print(f"[red]Configuration error:[/red] {e.code}")
        raise typer.Exit(1)

    db_path = Path(cfg.library.db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    meta = TMDBSource(token=cfg.metadata.tmdb_token)
    if not meta.is_available():
        console.print(
            "[yellow]Warning:[/yellow] TMDB API is not reachable. "
            "Check your tmdb_token in tapes.toml or TMDB_TOKEN environment variable."
        )

    service = ImportService(repo=repo, metadata_source=meta, config=cfg)
    summary = service.import_path(path)

    _print_summary(summary, cfg.import_.dry_run)

    if summary.get("errors"):
        raise typer.Exit(1)


def _print_summary(summary: dict, dry_run: bool) -> None:
    prefix = "[yellow]DRY RUN[/yellow] " if dry_run else ""

    if dry_run and summary.get("planned"):
        table = Table(title=f"{prefix}Planned imports", show_lines=False)
        table.add_column("Source", style="dim")
        table.add_column("Destination")
        table.add_column("Confidence", justify="right")
        for p in summary["planned"]:
            table.add_row(
                Path(p["source"]).name,
                p["dest"],
                f'{p["confidence"]:.0%}',
            )
        console.print(table)

    console.print(
        f"{prefix}"
        f"[green]{summary['imported']} imported[/green], "
        f"{summary['skipped']} skipped, "
        f"[red]{summary['errors']} errors[/red]"
    )

    if summary.get("unmatched"):
        console.print("[yellow]Unmatched files:[/yellow]")
        for f in summary["unmatched"]:
            console.print(f"  {f}")
