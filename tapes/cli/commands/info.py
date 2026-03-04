import typer
from pathlib import Path


def command(
    path: Path = typer.Argument(..., help="File to show info for."),
):
    """Show identified metadata for a file (runs pipeline if not in DB)."""
    typer.echo(f"info {path} (not yet implemented)")
