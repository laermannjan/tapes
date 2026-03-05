import sqlite3
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository

console = Console()


def command(
    session_id: Optional[int] = typer.Argument(None, help="Session ID to show. Defaults to last session."),
    full: bool = typer.Option(False, "--full", help="Show every file operation."),
    list_: bool = typer.Option(False, "--list", help="List all sessions."),
):
    """Show import session log."""
    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    if list_:
        _list_sessions(repo)
        return

    if session_id is None:
        sessions = repo.get_all_sessions()
        if not sessions:
            console.print("No sessions found.")
            return
        session = sessions[0]
    else:
        session = repo.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found.[/red]")
            raise typer.Exit(1)

    _show_session(repo, session, full=full)


def _list_sessions(repo: Repository) -> None:
    sessions = repo.get_all_sessions()
    if not sessions:
        console.print("No sessions found.")
        return

    table = Table(title="Import sessions")
    table.add_column("ID", justify="right")
    table.add_column("Started")
    table.add_column("State")
    table.add_column("Source")
    for s in sessions:
        state_style = {"completed": "green", "in_progress": "yellow"}.get(s["state"], "red")
        table.add_row(
            str(s["id"]),
            s["started_at"],
            f"[{state_style}]{s['state']}[/{state_style}]",
            s["source_path"],
        )
    console.print(table)


def _show_session(repo: Repository, session: dict, full: bool) -> None:
    console.print(f"Session [bold]{session['id']}[/bold]  {session['started_at']}  [{session['state']}]")
    console.print(f"  Source: {session['source_path']}")

    ops = repo.get_operations(session["id"])
    if not ops:
        console.print("  No operations recorded.")
        return

    by_state = {}
    for op in ops:
        by_state.setdefault(op["state"], []).append(op)

    summary_parts = []
    for state, items in sorted(by_state.items()):
        summary_parts.append(f"{len(items)} {state}")
    console.print(f"  Operations: {', '.join(summary_parts)}")

    if full:
        table = Table(show_lines=False)
        table.add_column("ID", justify="right")
        table.add_column("Source", style="dim")
        table.add_column("Dest")
        table.add_column("Type")
        table.add_column("State")
        for op in ops:
            table.add_row(
                str(op["id"]),
                op["source_path"],
                op.get("dest_path") or "",
                op["op_type"],
                op["state"],
            )
        console.print(table)
