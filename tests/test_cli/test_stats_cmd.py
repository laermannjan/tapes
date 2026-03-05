import sqlite3
import pytest
from typer.testing import CliRunner
from tapes.cli.main import app
from tapes.db.schema import init_db

runner = CliRunner()


@pytest.fixture
def db_with_items(tmp_path, monkeypatch):
    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, codec, resolution, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, 5000000000, datetime('now'))""",
        ("/movies/dune.mkv", "movie", "Dune", 2021, "hevc", "2160p"),
    )
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, codec, resolution,
           show, season, episode, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1000000000, datetime('now'))""",
        ("/tv/wire/s01e01.mkv", "tv", "The Target", 2002, "h264", "1080p", "The Wire", 1, 1),
    )
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, codec, resolution,
           show, season, episode, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1000000000, datetime('now'))""",
        ("/tv/wire/s01e02.mkv", "tv", "The Detail", 2002, "h264", "1080p", "The Wire", 1, 2),
    )
    conn.commit()
    conn.close()

    toml = tmp_path / "tapes.toml"
    toml.write_text(f'[library]\ndb_path = "{db_path}"\nmovies = "/movies"\ntv = "/tv"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestStatsCommand:
    def test_stats_shows_totals(self, db_with_items):
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_stats_shows_media_types(self, db_with_items):
        result = runner.invoke(app, ["stats"])
        assert "movie" in result.output.lower()
        assert "tv" in result.output.lower()

    def test_stats_shows_codecs(self, db_with_items):
        result = runner.invoke(app, ["stats"])
        assert "hevc" in result.output
        assert "h264" in result.output

    def test_stats_no_db(self, tmp_path, monkeypatch):
        toml = tmp_path / "tapes.toml"
        toml.write_text('[library]\ndb_path = "nonexistent.db"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No database" in result.output

    def test_stats_empty_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "library.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.close()

        toml = tmp_path / "tapes.toml"
        toml.write_text(f'[library]\ndb_path = "{db_path}"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower() or "0" in result.output
