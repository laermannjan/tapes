"""Tapes CLI -- typer application with import and scan commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from tapes.config import TapesConfig, load_config
from tapes.models import FileEntry, ImportGroup
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
    if config_file is not None:
        cfg = load_config(config_file)
    else:
        cfg = TapesConfig()

    if dry_run:
        cfg.dry_run = True

    groups = run_pipeline(path, config=cfg)

    if not groups:
        console.print("No video files found.")
        return

    if not no_tui:
        from tapes.ui import ReviewApp

        tui_app = ReviewApp(groups)
        tui_app.run()
        return

    _print_scan(path.resolve(), groups)


@app.command("scan")
def scan_cmd(
    path: Path = typer.Argument(..., help="Directory or file to scan"),
    find_companions: bool = typer.Option(
        False, "--find-companions", help="Include companion discovery (pass 3)"
    ),
    group: bool = typer.Option(
        False, "--group", help="Apply grouping (pass 4, implies --find-companions)"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
) -> None:
    """Scan and display import groups (no file operations).

    By default runs passes 1-2 (scan + metadata extraction).
    Use --find-companions to add companion discovery, --group to also merge groups.
    """
    cfg = load_config(config_file) if config_file else TapesConfig()
    cfg.dry_run = True

    groups = run_pipeline(
        path, config=cfg, companions=find_companions or group, group=group
    )

    if not groups:
        console.print("No video files found.")
        return

    _print_scan(path.resolve(), groups)


def _format_meta(entry: FileEntry, group: ImportGroup) -> Text:
    """Build the metadata column for a file entry."""
    # Use per-file metadata if available, fall back to group metadata
    meta = entry.metadata if entry.metadata else group.metadata
    parts: list[str] = []

    if entry.role == "video":
        if meta.media_type:
            parts.append(meta.media_type)
        if meta.title:
            parts.append(meta.title)
        if meta.year is not None:
            parts.append(str(meta.year))
        if meta.season is not None:
            ep = meta.episode
            if isinstance(ep, list):
                ep_str = "".join(f"E{e:02d}" for e in ep)
                parts.append(f"S{meta.season:02d}{ep_str}")
            elif ep is not None:
                parts.append(f"S{meta.season:02d}E{ep:02d}")
            else:
                parts.append(f"S{meta.season:02d}")
        if meta.part is not None:
            parts.append(f"CD{meta.part}")
    else:
        parts.append(entry.role)

    text = " │ ".join(parts)
    return Text(text, style="dim")


def _print_scan(root: Path, groups: list[ImportGroup]) -> None:
    """Print file-level scan results with metadata."""
    # Compute the relative display root
    try:
        display_root = f"./{root.relative_to(Path.cwd())}"
    except ValueError:
        display_root = str(root)

    console.print()
    console.print(f"  scanning [bold]{display_root}[/bold]")
    console.print()

    # Build paths relative to scan root
    rel_paths: dict[int, str] = {}
    max_path_len = 0
    for group in groups:
        for entry in group.files:
            try:
                rel = str(entry.path.relative_to(root))
            except ValueError:
                rel = entry.path.name
            rel_paths[id(entry)] = rel
            max_path_len = max(max_path_len, len(rel))

    # Cap alignment to something reasonable
    term_width = console.width or 120
    pad = min(max_path_len + 4, term_width - 40)

    for i, group in enumerate(groups):
        if i > 0:
            console.print()

        for entry in group.files:
            rel = rel_paths[id(entry)]
            meta_text = _format_meta(entry, group)

            line = Text()
            line.append("  ")
            if entry.role == "video":
                line.append(rel, style="white")
            else:
                line.append(rel, style="dim")
            spacing = max(pad - len(rel), 2)
            line.append(" " * spacing)
            line.append(meta_text)
            console.print(line)

    console.print()
    n_videos = sum(len(g.video_files) for g in groups)
    n_companions = sum(len(g.files) - len(g.video_files) for g in groups)
    summary_parts = [f"{len(groups)} group(s)", f"{n_videos} video(s)"]
    if n_companions:
        summary_parts.append(f"{n_companions} companion(s)")
    console.print(f"  [dim]{', '.join(summary_parts)}[/dim]")
    console.print()
