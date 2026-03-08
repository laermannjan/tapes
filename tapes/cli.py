"""Tapes CLI -- typer application."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from tapes.config import TapesConfig, load_config

app = typer.Typer(name="tapes", no_args_is_help=True, invoke_without_command=True)
console = Console(highlight=False)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """Tapes -- organise your movie and TV show files."""
    import logging

    if verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("tapes").setLevel(logging.DEBUG)


@app.command("import")
def import_cmd(
    path: Path = typer.Argument(..., help="Directory or file to import"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, no file operations ever"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Import video files into the library."""
    cfg = load_config(config_file) if config_file is not None else TapesConfig()

    if dry_run:
        cfg.dry_run = True

    from tapes.scanner import scan
    from tapes.ui.tree_app import TreeApp
    from tapes.ui.tree_model import build_tree

    resolved = path.resolve()
    files = scan(resolved, ignore_patterns=cfg.scan.ignore_patterns)
    if not files:
        console.print("No files found.")
        return

    model = build_tree(files, resolved)
    movie_template = cfg.library.movie_template
    tv_template = cfg.library.tv_template
    tui = TreeApp(
        model=model,
        movie_template=movie_template,
        tv_template=tv_template,
        root_path=resolved,
        auto_pipeline=True,
        config=cfg,
    )
    tui.run()


@app.command("tree")
def tree_cmd(
    path: Path = typer.Argument(..., help="Directory to scan"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Launch the tree TUI (dev command)."""
    from tapes.scanner import scan
    from tapes.ui.pipeline import run_guessit_pass
    from tapes.ui.tree_app import TreeApp
    from tapes.ui.tree_model import build_tree

    cfg = load_config(config_file) if config_file else TapesConfig()
    resolved = path.resolve()
    files = scan(resolved, ignore_patterns=cfg.scan.ignore_patterns)
    if not files:
        console.print("No files found.")
        return

    model = build_tree(files, resolved)
    run_guessit_pass(model)

    movie_template = cfg.library.movie_template
    tv_template = cfg.library.tv_template
    tui = TreeApp(
        model=model,
        movie_template=movie_template,
        tv_template=tv_template,
        root_path=resolved,
        config=cfg,
    )
    tui.run()
