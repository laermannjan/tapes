import sqlite3
import pytest
from typer.testing import CliRunner
from tapes.cli.main import app
from tapes.db.schema import init_db

runner = CliRunner()


class TestFieldsListCommand:
    def test_fields_lists_all(self):
        result = runner.invoke(app, ["fields"])
        assert result.exit_code == 0
        assert "title" in result.output
        assert "year" in result.output
        assert "season" in result.output
        assert "codec" in result.output
        assert "ext" in result.output

    def test_fields_shows_descriptions(self):
        result = runner.invoke(app, ["fields"])
        assert result.exit_code == 0
        # Check at least one description is present
        assert "release year" in result.output.lower() or "year" in result.output


class TestFieldsForFile:
    @pytest.fixture
    def db_with_file(self, tmp_path, monkeypatch):
        video = tmp_path / "dune.mkv"
        video.write_bytes(b"\x00" * 100)
        stat = video.stat()

        db_path = tmp_path / "library.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute(
            """INSERT INTO items (path, media_type, title, year, director,
               codec, resolution, hdr, mtime, size, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (str(video), "movie", "Dune", 2021, "Denis Villeneuve",
             "hevc", "2160p", 0, stat.st_mtime, stat.st_size),
        )
        conn.commit()
        conn.close()

        toml = tmp_path / "tapes.toml"
        toml.write_text(f'[library]\ndb_path = "{db_path}"\nmovies = "/movies"\n')
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_fields_for_file_in_db(self, db_with_file):
        video = db_with_file / "dune.mkv"
        result = runner.invoke(app, ["fields", str(video)])
        assert result.exit_code == 0
        assert "Dune" in result.output
        assert "2021" in result.output
        assert ".mkv" in result.output  # ext field

    def test_fields_file_not_found(self, db_with_file):
        result = runner.invoke(app, ["fields", "/nonexistent/file.mkv"])
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_fields_file_not_in_db(self, tmp_path, monkeypatch):
        video = tmp_path / "unknown.mkv"
        video.write_bytes(b"\x00" * 100)

        db_path = tmp_path / "library.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.close()

        toml = tmp_path / "tapes.toml"
        toml.write_text(f'[library]\ndb_path = "{db_path}"\nmovies = "/movies"\n')
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["fields", str(video)])
        assert result.exit_code == 0
        assert "not in library" in result.output.lower()

    def test_fields_no_db(self, tmp_path, monkeypatch):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"\x00" * 100)
        toml = tmp_path / "tapes.toml"
        toml.write_text('[library]\ndb_path = "nonexistent.db"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["fields", str(video)])
        assert result.exit_code == 0
        assert "No database" in result.output
