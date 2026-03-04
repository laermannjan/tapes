import typer
from pathlib import Path
from typing import Optional


def command(
    path: Path = typer.Argument(..., help="File, season directory, or show directory to modify."),
    id_: Optional[str] = typer.Option(None, "--id", help="Force a specific TMDB ID."),
    no_move: bool = typer.Option(False, "--no-move", help="Update metadata only, do not rename file."),
):
    """Re-identify a file and update its metadata and filename."""
    typer.echo(f"modify {path} (not yet implemented)")
