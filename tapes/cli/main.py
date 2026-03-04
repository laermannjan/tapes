import typer
from tapes.cli.commands import import_, move, check, modify, query, info, fields, stats, log

app = typer.Typer(name="tapes", help="Movie and TV show file organiser.")

app.command("import")(import_.command)
app.command("move")(move.command)
app.command("check")(check.command)
app.command("modify")(modify.command)
app.command("query")(query.command)
app.command("info")(info.command)
app.command("fields")(fields.command)
app.command("stats")(stats.command)
app.command("log")(log.command)
