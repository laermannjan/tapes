"""Smoke tests for the tapes CLI entry points."""

from __future__ import annotations

from typer.testing import CliRunner

from tapes.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "tapes" in result.output.lower()


def test_import_help():
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "import" in result.output.lower()


def test_tree_help():
    result = runner.invoke(app, ["tree", "--help"])
    assert result.exit_code == 0
    assert "tree" in result.output.lower()
