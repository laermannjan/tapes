"""Tapes CLI -- typer application."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from tapes.config import TapesConfig, load_config

app = typer.Typer(name="tapes", no_args_is_help=True, invoke_without_command=True)
console = Console(highlight=False)


@app.callback()
def main() -> None:
    """Tapes -- organise your movie and TV show files."""


@app.command("import")
def import_cmd(
    path: Path = typer.Argument(..., help="Directory or file to import"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview only, no file operations ever"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Import video files into the library."""
    if config_file is not None:
        cfg = load_config(config_file)
    else:
        cfg = TapesConfig()

    if dry_run:
        cfg.dry_run = True

    from tapes.scanner import scan
    from tapes.ui.tree_app import TreeApp
    from tapes.ui.tree_model import build_tree

    resolved = path.resolve()
    files = scan(resolved)
    if not files:
        console.print("No video files found.")
        return

    model = build_tree(files, resolved)
    movie_template = cfg.library.movie_template
    tv_template = cfg.library.tv_template
    tui = TreeApp(
        model=model,
        template=movie_template,
        root_path=resolved,
        auto_pipeline=True,
        movie_template=movie_template,
        tv_template=tv_template,
    )
    tui.run()


@app.command("tree")
def tree_cmd(
    path: Path = typer.Argument(..., help="Directory to scan"),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Launch the tree TUI (dev command)."""
    from tapes.metadata import extract_metadata
    from tapes.scanner import scan
    from tapes.ui.tree_app import TreeApp
    from tapes.ui.tree_model import build_tree

    cfg = load_config(config_file) if config_file else TapesConfig()
    resolved = path.resolve()
    files = scan(resolved)
    if not files:
        console.print("No video files found.")
        return

    model = build_tree(files, resolved)

    # Populate result from guessit metadata
    for file_node in model.all_files():
        meta = extract_metadata(file_node.path.name)
        result: dict[str, object] = {}
        if meta.title:
            result["title"] = meta.title
        if meta.year is not None:
            result["year"] = meta.year
        if meta.season is not None:
            result["season"] = meta.season
        if meta.episode is not None:
            result["episode"] = meta.episode
        if meta.media_type:
            result["media_type"] = meta.media_type
        for k, v in meta.raw.items():
            if v is not None:
                result[k] = v
        file_node.result = result

    movie_template = cfg.library.movie_template
    tv_template = cfg.library.tv_template
    tui = TreeApp(
        model=model,
        template=movie_template,
        root_path=resolved,
        movie_template=movie_template,
        tv_template=tv_template,
    )
    tui.run()
