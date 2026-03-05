import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.metadata.tmdb import TMDBSource
from tapes.events.bus import EventBus
from tapes.library.modifier import modify_item

console = Console()


def command(
    path: Path = typer.Argument(..., help="File, season directory, or show directory to modify."),
    id_: Optional[str] = typer.Option(None, "--id", help="Force a specific TMDB ID (e.g. tmdb:438631)."),
    no_move: bool = typer.Option(False, "--no-move", help="Update metadata only, do not rename file."),
):
    """Re-identify a file and update its metadata and filename."""
    if id_ is None:
        console.print("[red]--id is required.[/red] Interactive mode not yet supported.")
        console.print("Usage: tapes modify <path> --id tmdb:<id>")
        raise typer.Exit(1)

    path = path.resolve()
    cfg = load_config()

    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found. Nothing to modify.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    meta = TMDBSource(token=cfg.metadata.tmdb_token)
    bus = EventBus()

    result = modify_item(
        repo=repo, config=cfg, metadata_source=meta,
        path=path, tmdb_id=id_, no_move=no_move, event_bus=bus,
    )

    if not result.ok:
        console.print(f"[red]{result.error}[/red]")
        raise typer.Exit(1)

    if result.moved:
        console.print(f"[green]Updated and moved:[/green]")
        console.print(f"  {result.old_path} -> {result.new_path}")
    else:
        console.print(f"[green]Updated metadata for:[/green] {result.new_path}")
