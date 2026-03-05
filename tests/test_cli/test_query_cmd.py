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
        """INSERT INTO items (path, media_type, title, year, director, genre,
           codec, resolution, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1000, datetime('now'))""",
        ("/movies/dune.mkv", "movie", "Dune", 2021, "Denis Villeneuve", "Sci-Fi", "hevc", "2160p"),
    )
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, director, genre,
           show, season, episode, episode_title, codec, resolution, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 500, datetime('now'))""",
        ("/tv/wire/s01e01.mkv", "tv", "The Target", 2002, None, "Drama",
         "The Wire", 1, 1, "The Target", "h264", "1080p"),
    )
    conn.commit()
    conn.close()

    toml = tmp_path / "tapes.toml"
    toml.write_text(f'[library]\ndb_path = "{db_path}"\nmovies = "/movies"\ntv = "/tv"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestQueryCommand:
    def test_query_all(self, db_with_items):
        result = runner.invoke(app, ["query", ""])
        assert result.exit_code == 0
        assert "Dune" in result.output
        assert "The Wire" in result.output

    def test_query_by_title(self, db_with_items):
        result = runner.invoke(app, ["query", "title:Dune"])
        assert result.exit_code == 0
        assert "Dune" in result.output
        assert "The Wire" not in result.output

    def test_query_no_results(self, db_with_items):
        result = runner.invoke(app, ["query", "title:Nonexistent"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_query_with_limit(self, db_with_items):
        result = runner.invoke(app, ["query", "", "--limit", "1"])
        assert result.exit_code == 0
        assert "1 result(s)" in result.output

    def test_query_no_db(self, tmp_path, monkeypatch):
        toml = tmp_path / "tapes.toml"
        toml.write_text('[library]\ndb_path = "nonexistent.db"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["query", "title:Dune"])
        assert result.exit_code == 0
        assert "No database" in result.output
