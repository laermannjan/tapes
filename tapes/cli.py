"""Tapes CLI -- typer application with import and scan commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from tapes.config import TapesConfig, load_config
from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.pipeline import run_pipeline

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
        from tapes.metadata import extract_metadata
        from tapes.scanner import scan
        from tapes.ui.tree_app import TreeApp
        from tapes.ui.tree_model import build_tree

        resolved = path.resolve()
        files = scan(resolved)
        if not files:
            console.print("No video files found.")
            return

        model = build_tree(files, resolved)
        template = cfg.library.movie_template
        tui = TreeApp(
            model=model,
            template=template,
            root_path=resolved,
            auto_pipeline=True,
        )
        tui.run()
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


def _meta_parts(meta: FileMetadata) -> list[tuple[str, str]]:
    """Build (text, style) pairs for metadata display."""
    parts: list[tuple[str, str]] = []
    if meta.media_type:
        style = "cyan" if meta.media_type == "movie" else "magenta"
        parts.append((meta.media_type, style))
    if meta.title:
        parts.append((meta.title, "bold"))
    if meta.year is not None:
        parts.append((str(meta.year), "yellow"))
    if meta.season is not None:
        ep = meta.episode
        if isinstance(ep, list):
            ep_str = "".join(f"E{e:02d}" for e in ep)
            parts.append((f"S{meta.season:02d}{ep_str}", "green"))
        elif ep is not None:
            parts.append((f"S{meta.season:02d}E{ep:02d}", "green"))
        else:
            parts.append((f"S{meta.season:02d}", "green"))
    if meta.part is not None:
        parts.append((f"CD{meta.part}", "yellow"))
    return parts


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

    template = cfg.library.movie_template
    tui = TreeApp(model=model, template=template, root_path=resolved)
    tui.run()


def _print_scan(root: Path, groups: list[ImportGroup]) -> None:
    """Print file-level scan results with metadata."""
    try:
        display_root = f"./{root.relative_to(Path.cwd())}"
    except ValueError:
        display_root = str(root)

    console.print()
    header = Text("  scanning ")
    header.append(display_root, style="bold")
    console.print(header)
    console.print()

    # Pre-compute relative paths and find max length for alignment
    entries: list[tuple[FileEntry, ImportGroup, str]] = []
    max_path_len = 0
    for group in groups:
        for entry in group.files:
            try:
                rel = str(entry.path.relative_to(root))
            except ValueError:
                rel = entry.path.name
            entries.append((entry, group, rel))
            max_path_len = max(max_path_len, len(rel))

    term_width = console.width or 120
    pad = min(max_path_len + 2, term_width - 40)

    prev_group = None
    for entry, group, rel in entries:
        # Blank line between groups
        if prev_group is not None and group is not prev_group:
            console.print()
        prev_group = group

        line = Text()
        line.append("  ")

        if entry.role == "video":
            # Split into dir/ and filename
            p = Path(rel)
            if len(p.parts) > 1:
                dir_part = str(p.parent) + "/"
                line.append(dir_part, style="dim")
                line.append(p.name, style="white")
            else:
                line.append(rel, style="white")

            # Pad and add metadata
            spacing = max(pad - len(rel), 2)
            line.append(" " * spacing)

            meta = entry.metadata if entry.metadata else group.metadata
            parts = _meta_parts(meta)
            for j, (text, style) in enumerate(parts):
                if j > 0:
                    line.append(" ", style="dim")
                line.append(text, style=style)
        else:
            # Companion: dimmed path + role tag
            p = Path(rel)
            if len(p.parts) > 1:
                dir_part = str(p.parent) + "/"
                line.append(dir_part, style="dim")
                line.append(p.name, style="dim")
            else:
                line.append(rel, style="dim")

            spacing = max(pad - len(rel), 2)
            line.append(" " * spacing)
            line.append(entry.role, style="dim italic")

        console.print(line)

    console.print()
    n_videos = sum(len(g.video_files) for g in groups)
    n_companions = sum(len(g.files) - len(g.video_files) for g in groups)

    summary = Text("  ")
    summary.append(f"{len(groups)}", style="bold")
    summary.append(f" groups  ", style="dim")
    summary.append(f"{n_videos}", style="bold")
    summary.append(f" videos", style="dim")
    if n_companions:
        summary.append(f"  {n_companions}", style="bold")
        summary.append(f" companions", style="dim")
    console.print(summary)
    console.print()
