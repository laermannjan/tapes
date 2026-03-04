import typer
from typing import Optional


def command(
    session_id: Optional[int] = typer.Argument(None, help="Session ID to show. Defaults to last session."),
    full: bool = typer.Option(False, "--full", help="Show every file operation."),
    list_: bool = typer.Option(False, "--list", help="List all sessions."),
):
    """Show import session log."""
    typer.echo("log (not yet implemented)")
