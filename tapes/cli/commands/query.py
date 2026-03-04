import typer
from typing import Optional


def command(
    query_str: str = typer.Argument(..., metavar="QUERY", help="Query string, e.g. 'genre:thriller year:>2010'."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Maximum results to show."),
):
    """Query the library with structured search expressions."""
    typer.echo(f"query '{query_str}' (not yet implemented)")
