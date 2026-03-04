import typer
from pathlib import Path
from typing import Optional


def command(
    path: Optional[Path] = typer.Argument(None, help="File to show available fields for."),
):
    """List all template fields available (optionally for a specific file)."""
    typer.echo("fields (not yet implemented)")
