import typer
from pathlib import Path
from typing import Optional


def command(
    path: Path = typer.Argument(..., help="Path to scan for media files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes."),
    interactive: bool = typer.Option(False, "--interactive", help="Force interactive for all groups."),
    no_db: bool = typer.Option(False, "--no-db", help="Identify and rename only, no DB writes."),
    mode: Optional[str] = typer.Option(None, "--mode", help="copy|move|link|hardlink"),
    confidence: Optional[float] = typer.Option(None, "--confidence", help="Override confidence threshold."),
):
    """Import media files from PATH."""
    typer.echo(f"import {path} (not yet implemented)")
