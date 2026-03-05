import sqlite3
import pytest
from pathlib import Path
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.check import check_library, CheckResult


@pytest.fixture
def setup(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)
    library_root = tmp_path / "movies"
    library_root.mkdir()
    return conn, repo, library_root


def _insert_item(conn, path, title="Film", year=2020):
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, mtime, size, imported_at)
           VALUES (?, 'movie', ?, ?, 0, 0, datetime('now'))""",
        (str(path), title, year),
    )
    conn.commit()


class TestMissingFiles:
    def test_detects_missing_file(self, setup):
        conn, repo, root = setup
        _insert_item(conn, root / "Gone.mkv")
        # File does not exist on disk
        result = check_library(repo, [root])
        assert len(result.missing) == 1
        assert "Gone.mkv" in result.missing[0]

    def test_present_file_not_reported(self, setup):
        conn, repo, root = setup
        video = root / "Present.mkv"
        video.touch()
        _insert_item(conn, video)
        result = check_library(repo, [root])
        assert result.missing == []

    def test_multiple_missing(self, setup):
        conn, repo, root = setup
        _insert_item(conn, root / "A.mkv", "A")
        _insert_item(conn, root / "B.mkv", "B")
        (root / "B.mkv").touch()  # only B exists
        result = check_library(repo, [root])
        assert len(result.missing) == 1
        assert "A.mkv" in result.missing[0]


class TestOrphanedFiles:
    def test_detects_orphan_video(self, setup):
        conn, repo, root = setup
        orphan = root / "Unknown.mkv"
        orphan.touch()
        result = check_library(repo, [root])
        assert len(result.orphaned) == 1
        assert "Unknown.mkv" in result.orphaned[0]

    def test_ignores_non_video_files(self, setup):
        conn, repo, root = setup
        (root / "readme.txt").touch()
        (root / "poster.jpg").touch()
        result = check_library(repo, [root])
        assert result.orphaned == []

    def test_known_file_not_orphaned(self, setup):
        conn, repo, root = setup
        video = root / "Known.mkv"
        video.touch()
        _insert_item(conn, video)
        result = check_library(repo, [root])
        assert result.orphaned == []

    def test_recursive_orphan_detection(self, setup):
        conn, repo, root = setup
        sub = root / "subdir"
        sub.mkdir()
        orphan = sub / "deep.mkv"
        orphan.touch()
        result = check_library(repo, [root])
        assert len(result.orphaned) == 1


class TestMultipleRoots:
    def test_checks_both_movie_and_tv_roots(self, setup):
        conn, repo, root = setup
        tv_root = root.parent / "tv"
        tv_root.mkdir()
        _insert_item(conn, root / "Missing.mkv")
        (tv_root / "Orphan.mkv").touch()
        result = check_library(repo, [root, tv_root])
        assert len(result.missing) == 1
        assert len(result.orphaned) == 1


class TestCleanLibrary:
    def test_no_issues(self, setup):
        conn, repo, root = setup
        video = root / "Good.mkv"
        video.touch()
        _insert_item(conn, video)
        result = check_library(repo, [root])
        assert result.missing == []
        assert result.orphaned == []
        assert result.ok

    def test_empty_library(self, setup):
        conn, repo, root = setup
        result = check_library(repo, [root])
        assert result.ok
