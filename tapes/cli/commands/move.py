import typer
from pathlib import Path
from typing import Optional


def command(
    path: Optional[Path] = typer.Argument(None, help="Limit move to files under PATH."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes."),
    no_db: bool = typer.Option(False, "--no-db", help="Move files without updating DB."),
):
    """Re-apply templates and move all library files to their correct locations."""
    typer.echo("move (not yet implemented)")
