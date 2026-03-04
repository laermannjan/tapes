import sqlite3
import pytest
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.importer.session import ImportSession


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return Repository(conn)


def test_create_session(repo):
    session = ImportSession.create(repo, "/media/downloads")
    assert session.session_id is not None
    assert session.session_id > 0


def test_session_complete(repo):
    session = ImportSession.create(repo, "/media/downloads")
    session.complete()

    rows = repo._conn.execute(
        "SELECT state, finished_at FROM sessions WHERE id = ?", (session.session_id,)
    ).fetchall()
    assert rows[0]["state"] == "completed"
    assert rows[0]["finished_at"] is not None


def test_session_abort(repo):
    session = ImportSession.create(repo, "/media/downloads")
    session.abort()

    row = repo._conn.execute(
        "SELECT state FROM sessions WHERE id = ?", (session.session_id,)
    ).fetchone()
    assert row["state"] == "aborted"


def test_add_operation(repo):
    session = ImportSession.create(repo, "/media/downloads")
    op_id = session.add_operation("/media/downloads/movie.mkv", "copy")
    assert op_id is not None

    row = repo._conn.execute(
        "SELECT source_path, op_type FROM operations WHERE id = ?", (op_id,)
    ).fetchone()
    assert row["source_path"] == "/media/downloads/movie.mkv"
    assert row["op_type"] == "copy"


def test_update_operation(repo):
    session = ImportSession.create(repo, "/media/downloads")
    op_id = session.add_operation("/media/downloads/movie.mkv", "move")

    session.update_operation(op_id, state="done", dest_path="/library/movie.mkv")

    row = repo._conn.execute(
        "SELECT state, dest_path FROM operations WHERE id = ?", (op_id,)
    ).fetchone()
    assert row["state"] == "done"
    assert row["dest_path"] == "/library/movie.mkv"


def test_find_in_progress(repo):
    session = ImportSession.create(repo, "/media/downloads")
    in_progress = ImportSession.find_in_progress(repo)
    assert any(s["id"] == session.session_id for s in in_progress)

    session.complete()
    in_progress = ImportSession.find_in_progress(repo)
    assert not any(s["id"] == session.session_id for s in in_progress)
