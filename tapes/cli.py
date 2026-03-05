"""Tapes CLI -- typer application with import command."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tapes.config import TapesConfig, load_config
from tapes.pipeline import run_pipeline

app = typer.Typer(name="tapes", no_args_is_help=True, invoke_without_command=True)
console = Console()


@app.callback()
def main() -> None:
    """Tapes -- organise your movie and TV show files."""


@app.command("import")
def import_cmd(
    path: Path = typer.Argument(..., help="Directory or file to import"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview only, no file operations ever"
    ),
    no_tui: bool = typer.Option(
        False, "--no-tui", help="Plain text output instead of TUI"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Import video files into the library."""
    # Load config
    if config_file is not None:
        cfg = load_config(config_file)
    else:
        cfg = TapesConfig()

    if dry_run:
        cfg.dry_run = True

    # Run the pipeline
    groups = run_pipeline(path, config=cfg)

    if not groups:
        console.print("No video files found.")
        return

    if not no_tui:
        from tapes.ui import ReviewApp

        tui_app = ReviewApp(groups)
        tui_app.run()
        return

    _print_plain(groups)


@app.command("scan")
def scan_cmd(
    path: Path = typer.Argument(..., help="Directory or file to scan"),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Scan and display import groups (no file operations)."""
    cfg = load_config(config_file) if config_file else TapesConfig()
    cfg.dry_run = True

    groups = run_pipeline(path, config=cfg)

    if not groups:
        console.print("No video files found.")
        return

    _print_plain(groups)


def _print_plain(groups):
    """Print groups as a Rich table."""
    table = Table(title="Import Groups")
    table.add_column("Type")
    table.add_column("Label")
    table.add_column("Videos", justify="right")
    table.add_column("Companions", justify="right")

    for group in groups:
        n_videos = len(group.video_files)
        n_companions = len(group.files) - n_videos
        table.add_row(
            group.group_type.value,
            group.label,
            str(n_videos),
            str(n_companions),
        )

    console.print(table)
    console.print(f"{len(groups)} group(s) found.")
