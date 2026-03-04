import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            path           TEXT    NOT NULL,
            media_type     TEXT    NOT NULL,
            tmdb_id        INTEGER,
            title          TEXT,
            year           INTEGER,
            show           TEXT,
            season         INTEGER,
            episode        INTEGER,
            episode_title  TEXT,
            director       TEXT,
            genre          TEXT,
            edition        TEXT,
            codec          TEXT,
            resolution     TEXT,
            audio          TEXT,
            hdr            INTEGER DEFAULT 0,
            match_source   TEXT,
            confidence     REAL,
            mtime          REAL    NOT NULL DEFAULT 0,
            size           INTEGER NOT NULL DEFAULT 0,
            imported_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS seasons (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_show_id   INTEGER NOT NULL,
            season_number  INTEGER NOT NULL,
            episode_count  INTEGER NOT NULL,
            UNIQUE (tmdb_show_id, season_number)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            finished_at  TEXT,
            state        TEXT    NOT NULL DEFAULT 'in_progress',
            source_path  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   INTEGER NOT NULL REFERENCES sessions(id),
            source_path  TEXT    NOT NULL,
            dest_path    TEXT,
            op_type      TEXT    NOT NULL,
            state        TEXT    NOT NULL DEFAULT 'pending',
            item_id      INTEGER REFERENCES items(id),
            error        TEXT,
            updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)
