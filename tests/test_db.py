import sqlite3
import pytest
from tapes.db.schema import init_db, get_schema_version
from tapes.db.repository import Repository, ItemRecord


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_init_creates_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "library.db")
    init_db(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "schema_version" in tables
    assert "items" in tables
    assert "sessions" in tables
    assert "operations" in tables
    assert "seasons" in tables


def test_schema_version(tmp_path):
    conn = sqlite3.connect(tmp_path / "library.db")
    init_db(conn)
    assert get_schema_version(conn) == 1


def test_init_idempotent(tmp_path):
    """Calling init_db twice must not raise."""
    conn = sqlite3.connect(tmp_path / "library.db")
    init_db(conn)
    init_db(conn)
    assert get_schema_version(conn) == 1


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    conn = sqlite3.connect(tmp_path / "library.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return Repository(conn)


def _make_item(**kwargs) -> ItemRecord:
    defaults = dict(
        id=None, path="/movies/Dune.mkv", media_type="movie",
        tmdb_id=438631, title="Dune", year=2021,
        show=None, season=None, episode=None, episode_title=None,
        director="Denis Villeneuve", genre="Science Fiction",
        edition=None, codec="H.265", resolution="2160p",
        audio="TrueHD", hdr=1, match_source="tmdb",
        confidence=0.97, mtime=1700000000.0, size=10_000_000_000,
        imported_at="2026-03-04T12:00:00",
    )
    defaults.update(kwargs)
    return ItemRecord(**defaults)


def test_find_by_path_stat_miss(repo):
    assert repo.find_by_path_stat("/nonexistent.mkv", 0.0, 0) is None


def test_upsert_and_find(repo):
    item = _make_item()
    row_id = repo.upsert_item(item)
    assert isinstance(row_id, int)
    found = repo.find_by_path_stat("/movies/Dune.mkv", 1700000000.0, 10_000_000_000)
    assert found is not None
    assert found.title == "Dune"
    assert found.confidence == pytest.approx(0.97)


def test_upsert_updates_existing(repo):
    item = _make_item()
    repo.upsert_item(item)
    updated = _make_item(title="Dune: Updated", confidence=0.99)
    repo.upsert_item(updated)
    found = repo.find_by_path_stat("/movies/Dune.mkv", 1700000000.0, 10_000_000_000)
    assert found.title == "Dune: Updated"
    assert found.confidence == pytest.approx(0.99)


def test_create_session(repo):
    session_id = repo.create_session("/source/dir")
    assert isinstance(session_id, int)


def test_create_and_update_operation(repo):
    session_id = repo.create_session("/source/dir")
    op_id = repo.create_operation(session_id, "/source/Dune.mkv", "copy")
    assert isinstance(op_id, int)
    repo.update_operation(op_id, state="done", dest_path="/movies/Dune (2021)/Dune (2021).mkv")


def test_get_in_progress_sessions(repo):
    repo.create_session("/src1")
    repo.create_session("/src2")
    sessions = repo.get_in_progress_sessions()
    assert len(sessions) == 2
