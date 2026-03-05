import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.service import LibraryService

console = Console()


def command(
    query_str: str = typer.Argument(..., metavar="QUERY", help="Query string, e.g. 'genre:thriller year:>2010'."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Maximum results to show."),
):
    """Query the library with structured search expressions."""
    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)
    svc = LibraryService(repo)

    items = svc.query(query_str)
    if limit is not None:
        items = items[:limit]

    if not items:
        console.print("[yellow]No results.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"{len(items)} result(s)")
    table.add_column("Title", style="bold")
    table.add_column("Year")
    table.add_column("Type")
    table.add_column("Show")
    table.add_column("S/E")
    table.add_column("Resolution")
    table.add_column("Codec")
    table.add_column("Path", style="dim")

    for item in items:
        se = ""
        if item.season is not None:
            se = f"S{item.season:02d}"
            if item.episode is not None:
                se += f"E{item.episode:02d}"
        table.add_row(
            item.title or "",
            str(item.year) if item.year else "",
            item.media_type,
            item.show or "",
            se,
            item.resolution or "",
            item.codec or "",
            item.path,
        )

    console.print(table)
