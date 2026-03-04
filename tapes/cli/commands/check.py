import typer


def command(
    fix: bool = typer.Option(False, "--fix", help="Auto-fix detectable issues."),
):
    """Check library integrity — orphaned files, missing files, DB mismatches."""
    typer.echo("check (not yet implemented)")
