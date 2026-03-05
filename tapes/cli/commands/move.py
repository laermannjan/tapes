import sqlite3
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.mover import plan_moves, execute_moves

console = Console()


def command(
    path: Optional[Path] = typer.Argument(None, help="Limit move to files under PATH."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes."),
):
    """Re-apply templates and move all library files to their correct locations."""
    cfg = load_config()

    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found. Nothing to move.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    moves = plan_moves(repo, cfg)

    if not moves:
        console.print("[green]All files are already at their correct locations.[/green]")
        return

    result = execute_moves(moves, repo, dry_run=dry_run)

    if dry_run:
        table = Table(title=f"[yellow]DRY RUN[/yellow] Would move {len(result.planned)} file(s)")
        table.add_column("From", style="dim")
        table.add_column("To")
        for p in result.planned:
            table.add_row(p["old_path"], p["new_path"])
        console.print(table)
    else:
        console.print(
            f"[green]{result.moved} moved[/green], "
            f"{result.skipped} skipped, "
            f"[red]{result.failed} failed[/red]"
        )
