import sqlite3
import typer
from pathlib import Path
from rich.console import Console

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.check import check_library

console = Console()


def command(
    fix: bool = typer.Option(False, "--fix", help="Auto-fix detectable issues."),
):
    """Check library integrity -- orphaned files, missing files."""
    cfg = load_config()

    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found. Nothing to check.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    roots = []
    if cfg.library.movies:
        roots.append(Path(cfg.library.movies).expanduser())
    if cfg.library.tv:
        roots.append(Path(cfg.library.tv).expanduser())

    result = check_library(repo, roots)

    if result.ok:
        console.print("[green]Library is clean.[/green]")
        return

    if result.missing:
        console.print(f"[red]{len(result.missing)} missing file(s):[/red]")
        for p in result.missing:
            console.print(f"  {p}")

    if result.orphaned:
        console.print(f"[yellow]{len(result.orphaned)} orphaned file(s):[/yellow]")
        for p in result.orphaned:
            console.print(f"  {p}")

    raise typer.Exit(1)
