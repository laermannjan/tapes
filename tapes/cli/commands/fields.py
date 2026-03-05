import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository

console = Console()

_FIELD_DESCRIPTIONS = [
    ("title", "Movie or episode title"),
    ("year", "Release year"),
    ("show", "TV show name (TV only)"),
    ("season", "Season number (TV only)"),
    ("episode", "Episode number (TV only)"),
    ("episode_title", "Episode title (TV only)"),
    ("director", "Primary director"),
    ("genre", "Genres from TMDB"),
    ("edition", "Edition (Director's Cut, Extended, etc.)"),
    ("codec", "Video codec (h264, hevc, vp9)"),
    ("resolution", "Video resolution (720p, 1080p, 2160p)"),
    ("audio", "Audio codec/language"),
    ("hdr", "HDR metadata present (0 or 1)"),
    ("media_type", "movie or tv"),
    ("ext", "File extension (.mkv, .mp4, etc.)"),
]


def command(
    path: Optional[Path] = typer.Argument(None, help="File to show available fields for."),
):
    """List all template fields available (optionally for a specific file)."""
    if path is None:
        _list_fields()
        return

    _show_fields_for_file(path.resolve())


def _list_fields() -> None:
    table = Table(title="Template Fields")
    table.add_column("Field", style="bold")
    table.add_column("Description")
    for name, desc in _FIELD_DESCRIPTIONS:
        table.add_row(name, desc)
    console.print(table)


def _show_fields_for_file(path: Path) -> None:
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
    if not item:
        items = repo.query_items("path = ?", [str(path)])
        item = items[0] if items else None

    if not item:
        console.print(f"[yellow]File not in library: {path}[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Fields for: {path.name}", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()

    field_names = [
        "title", "year", "show", "season", "episode", "episode_title",
        "director", "genre", "edition", "codec", "resolution", "audio",
        "hdr", "media_type",
    ]
    for name in field_names:
        value = getattr(item, name, None)
        if name == "hdr":
            value = "yes" if value else "no"
        table.add_row(name, str(value) if value is not None else "-")

    # Computed: ext
    table.add_row("ext", path.suffix)

    console.print(table)
