from typer.testing import CliRunner
from tapes.cli.main import app

runner = CliRunner()


def test_app_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_import_help():
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_move_help():
    result = runner.invoke(app, ["move", "--help"])
    assert result.exit_code == 0


def test_modify_help():
    result = runner.invoke(app, ["modify", "--help"])
    assert result.exit_code == 0
