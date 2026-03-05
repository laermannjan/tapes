import sqlite3
from dataclasses import dataclass


@dataclass
class ItemRecord:
    id: int | None
    path: str
    media_type: str
    tmdb_id: int | None
    title: str | None
    year: int | None
    show: str | None
    season: int | None
    episode: int | None
    episode_title: str | None
    director: str | None
    genre: str | None
    edition: str | None
    codec: str | None
    resolution: str | None
    audio: str | None
    hdr: int
    match_source: str | None
    confidence: float | None
    mtime: float
    size: int
    imported_at: str


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def find_by_path_stat(self, path: str, mtime: float, size: int) -> ItemRecord | None:
        """Step 1 of identification pipeline: DB cache lookup."""
        row = self._conn.execute(
            "SELECT * FROM items WHERE path = ? AND mtime = ? AND size = ?",
            (path, mtime, size),
        ).fetchone()
        return _row_to_item(row) if row else None

    def upsert_item(self, item: ItemRecord) -> int:
        """Insert or update an item by path. Returns the row id."""
        existing = self._conn.execute(
            "SELECT id FROM items WHERE path = ?", (item.path,)
        ).fetchone()

        if existing:
            self._conn.execute(
                """UPDATE items SET
                    media_type=?, tmdb_id=?, title=?, year=?, show=?, season=?,
                    episode=?, episode_title=?, director=?, genre=?, edition=?,
                    codec=?, resolution=?, audio=?, hdr=?, match_source=?,
                    confidence=?, mtime=?, size=?, imported_at=?
                WHERE path=?""",
                (
                    item.media_type, item.tmdb_id, item.title, item.year,
                    item.show, item.season, item.episode, item.episode_title,
                    item.director, item.genre, item.edition, item.codec,
                    item.resolution, item.audio, item.hdr, item.match_source,
                    item.confidence, item.mtime, item.size, item.imported_at,
                    item.path,
                ),
            )
            self._conn.commit()
            return existing[0]

        cur = self._conn.execute(
            """INSERT INTO items (
                path, media_type, tmdb_id, title, year, show, season,
                episode, episode_title, director, genre, edition, codec,
                resolution, audio, hdr, match_source, confidence, mtime, size, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.path, item.media_type, item.tmdb_id, item.title, item.year,
                item.show, item.season, item.episode, item.episode_title,
                item.director, item.genre, item.edition, item.codec,
                item.resolution, item.audio, item.hdr, item.match_source,
                item.confidence, item.mtime, item.size, item.imported_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_all_items(self) -> list[ItemRecord]:
        rows = self._conn.execute("SELECT * FROM items").fetchall()
        return [_row_to_item(r) for r in rows]

    def create_session(self, source_path: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO sessions (source_path) VALUES (?)", (source_path,)
        )
        self._conn.commit()
        return cur.lastrowid

    def update_session_state(self, session_id: int, state: str, finished_at: str | None = None) -> None:
        self._conn.execute(
            "UPDATE sessions SET state = ?, finished_at = ? WHERE id = ?",
            (state, finished_at, session_id),
        )
        self._conn.commit()

    def create_operation(self, session_id: int, source_path: str, op_type: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO operations (session_id, source_path, op_type) VALUES (?, ?, ?)",
            (session_id, source_path, op_type),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_operation(self, op_id: int, **kwargs) -> None:
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        self._conn.execute(
            f"UPDATE operations SET {cols}, updated_at = datetime('now') WHERE id = ?",
            (*kwargs.values(), op_id),
        )
        self._conn.commit()

    def get_in_progress_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE state = 'in_progress'"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_operations(self, session_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM operations WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _row_to_item(row) -> ItemRecord:
    # Support both sqlite3.Row and plain tuples
    if hasattr(row, "keys"):
        return ItemRecord(**{k: row[k] for k in row.keys()})
    return ItemRecord(*row)
