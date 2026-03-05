import sqlite3
import pytest
from pathlib import Path
from tapes.db.schema import init_db
from tapes.db.repository import Repository, ItemRecord
from tapes.config.schema import TapesConfig, LibraryConfig, TemplatesConfig
from tapes.library.mover import plan_moves, execute_moves


@pytest.fixture
def setup(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    movies_root = tmp_path / "movies"
    movies_root.mkdir()

    cfg = TapesConfig(
        library=LibraryConfig(movies=str(movies_root)),
        templates=TemplatesConfig(movie="{title} ({year})/{title} ({year}){ext}"),
    )
    return repo, conn, cfg, movies_root


def _insert_item(conn, path, title="Film", year=2020, media_type="movie"):
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, 0, 0, datetime('now'))""",
        (str(path), media_type, title, year),
    )
    conn.commit()


class TestPlanMoves:
    def test_detects_needed_move(self, setup):
        repo, conn, cfg, root = setup
        old_path = root / "wrong_name.mkv"
        old_path.touch()
        _insert_item(conn, old_path, "Dune", 2021)
        moves = plan_moves(repo, cfg)
        assert len(moves) == 1
        assert "Dune (2021)" in moves[0]["new_path"]

    def test_no_move_when_path_correct(self, setup):
        repo, conn, cfg, root = setup
        correct = root / "Dune (2021)" / "Dune (2021).mkv"
        correct.parent.mkdir(parents=True)
        correct.touch()
        _insert_item(conn, correct, "Dune", 2021)
        moves = plan_moves(repo, cfg)
        assert len(moves) == 0

    def test_template_change_triggers_moves(self, setup):
        repo, conn, cfg, root = setup
        old = root / "Dune (2021)" / "Dune (2021).mkv"
        old.parent.mkdir(parents=True)
        old.touch()
        _insert_item(conn, old, "Dune", 2021)

        cfg.templates.movie = "{title}/{title} ({year}){ext}"
        moves = plan_moves(repo, cfg)
        assert len(moves) == 1
        assert "Dune/Dune (2021).mkv" in moves[0]["new_path"]


class TestDryRun:
    def test_dry_run_returns_planned(self, setup):
        repo, conn, cfg, root = setup
        _insert_item(conn, root / "old.mkv", "Dune", 2021)
        moves = plan_moves(repo, cfg)
        result = execute_moves(moves, repo, dry_run=True)
        assert len(result.planned) == 1
        assert result.moved == 0

    def test_dry_run_does_not_touch_files(self, setup):
        repo, conn, cfg, root = setup
        old = root / "old.mkv"
        old.touch()
        _insert_item(conn, old, "Dune", 2021)
        moves = plan_moves(repo, cfg)
        execute_moves(moves, repo, dry_run=True)
        assert old.exists()


class TestExecuteMoves:
    def test_moves_file_and_updates_db(self, setup):
        repo, conn, cfg, root = setup
        old = root / "old.mkv"
        old.write_bytes(b"video data")
        _insert_item(conn, old, "Dune", 2021)

        moves = plan_moves(repo, cfg)
        result = execute_moves(moves, repo)

        assert result.moved == 1
        assert not old.exists()
        new = root / "Dune (2021)" / "Dune (2021).mkv"
        assert new.exists()
        assert new.read_bytes() == b"video data"

        # DB should be updated
        items = repo.get_all_items()
        assert items[0].path == str(new)

    def test_missing_source_skips(self, setup):
        repo, conn, cfg, root = setup
        _insert_item(conn, root / "gone.mkv", "Dune", 2021)
        moves = plan_moves(repo, cfg)
        result = execute_moves(moves, repo)
        assert result.skipped == 1
        assert result.moved == 0

    def test_multiple_files(self, setup):
        repo, conn, cfg, root = setup
        a = root / "a.mkv"
        b = root / "b.mkv"
        a.write_bytes(b"data a")
        b.write_bytes(b"data b")
        _insert_item(conn, a, "Film A", 2020)
        _insert_item(conn, b, "Film B", 2021)

        moves = plan_moves(repo, cfg)
        result = execute_moves(moves, repo)
        assert result.moved == 2

    def test_creates_parent_dirs(self, setup):
        repo, conn, cfg, root = setup
        old = root / "flat.mkv"
        old.write_bytes(b"data")
        _insert_item(conn, old, "Deep Movie", 2023)

        moves = plan_moves(repo, cfg)
        execute_moves(moves, repo)

        new = root / "Deep Movie (2023)" / "Deep Movie (2023).mkv"
        assert new.exists()
