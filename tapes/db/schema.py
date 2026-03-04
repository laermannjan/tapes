import sqlite3

CURRENT_VERSION = 1


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and run pending migrations."""
    _create_schema_version(conn)
    version = get_schema_version(conn)
    _run_migrations(conn, from_version=version)


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0


def _create_schema_version(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)
    """)
    if not conn.execute("SELECT * FROM schema_version").fetchone():
        conn.execute("INSERT INTO schema_version VALUES (0)")
    conn.commit()


def _run_migrations(conn: sqlite3.Connection, from_version: int) -> None:
    from tapes.db.migrations import migration_001
    migrations = [
        (1, migration_001.up),
    ]
    for version, fn in migrations:
        if from_version < version:
            fn(conn)
            conn.execute("UPDATE schema_version SET version = ?", (version,))
            conn.commit()
