import sqlite3
from collections import Counter
from pathlib import Path

import typer
from rich.console import Console

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository

console = Console()


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def command():
    """Show library statistics."""
    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    items = repo.get_all_items()
    if not items:
        console.print("[yellow]Library is empty.[/yellow]")
        raise typer.Exit(0)

    total = len(items)
    type_counts = Counter(i.media_type for i in items)
    codec_counts = Counter(i.codec for i in items if i.codec)
    res_counts = Counter(i.resolution for i in items if i.resolution)
    total_size = sum(i.size for i in items)

    # TV details
    tv_items = [i for i in items if i.media_type == "tv"]
    shows = {i.show for i in tv_items if i.show}
    seasons = {(i.show, i.season) for i in tv_items if i.show and i.season is not None}

    console.print("[bold]Library Statistics[/bold]\n")

    console.print(f"  Total items:  {total}")
    for mt, count in type_counts.most_common():
        extra = ""
        if mt == "tv":
            extra = f"  ({len(shows)} show(s), {len(seasons)} season(s))"
        console.print(f"  {mt:12s}   {count}{extra}")

    console.print(f"\n  Total size:   {_human_size(total_size)}")

    if codec_counts:
        top_codecs = ", ".join(f"{c} ({n})" for c, n in codec_counts.most_common(5))
        console.print(f"  Codecs:       {top_codecs}")

    if res_counts:
        top_res = ", ".join(f"{r} ({n})" for r, n in res_counts.most_common(5))
        console.print(f"  Resolutions:  {top_res}")
