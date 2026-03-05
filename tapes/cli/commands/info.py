import sqlite3
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository, ItemRecord

console = Console()

_DISPLAY_FIELDS = [
    ("Path", "path"),
    ("Media type", "media_type"),
    ("TMDB ID", "tmdb_id"),
    ("Title", "title"),
    ("Year", "year"),
    ("Show", "show"),
    ("Season", "season"),
    ("Episode", "episode"),
    ("Episode title", "episode_title"),
    ("Director", "director"),
    ("Genre", "genre"),
    ("Edition", "edition"),
    ("Codec", "codec"),
    ("Resolution", "resolution"),
    ("Audio", "audio"),
    ("HDR", "hdr"),
    ("Match source", "match_source"),
    ("Confidence", "confidence"),
]


def _format_value(field: str, value) -> str:
    if value is None:
        return "-"
    if field == "hdr":
        return "yes" if value else "no"
    if field == "confidence" and isinstance(value, float):
        return f"{value:.0%}"
    return str(value)


def _print_item(item: ItemRecord) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    for label, field in _DISPLAY_FIELDS:
        value = getattr(item, field)
        table.add_row(label, _format_value(field, value))
    console.print(table)


def command(
    path: Path = typer.Argument(..., help="File to show info for."),
):
    """Show identified metadata for a file."""
    path = path.resolve()

    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    stat = path.stat()
    item = repo.find_by_path_stat(str(path), stat.st_mtime, stat.st_size)

    if item:
        _print_item(item)
        return

    # Not in DB - try path-only lookup (file may have been modified)
    items = repo.query_items("path = ?", [str(path)])
    if items:
        _print_item(items[0])
        return

    console.print(f"[yellow]File not in library: {path}[/yellow]")
    console.print("Run [bold]tapes import[/bold] to add it.")
