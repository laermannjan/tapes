# Tapes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool for organising movie and TV show files — identifying, renaming, moving, and tracking them in a queryable local library.

**Architecture:** CLI (typer + rich) → Services → Core (EventBus, Config, DB) → Adapters (MetadataSource ABC). Identification pipeline: DB cache → NFO scan → guessit → TMDB query → interactive fallback. Plugin system via Python entry points / EventBus.

**Tech Stack:** Python 3.11+, typer, rich, guessit, pymediainfo, requests, pydantic, sqlite3 (stdlib), tomllib (stdlib), importlib.metadata (stdlib)

**Design doc:** `docs/plans/2026-03-04-tapes-design.md`

> **Implementation notes:**
> - Follow TDD: write failing test → implement → pass → commit.
> - Each task ends with a commit.
> - `xattr` is NOT used anywhere — identification caching is done via DB lookup (path + mtime + size).
> - All file writes go through the session log (operations table) — no file is touched without a session record.
> - Pre-flight collision detection runs before any file operation in both `import` and `tapes move`.

## Progress (updated 2026-03-04)

| Task | Description | Status |
|------|-------------|--------|
| 1  | Project setup | done |
| 2  | CLI skeleton | done |
| 3  | Config schema and loading | done |
| 4  | SQLite schema and repository | done |
| 5  | Filename parsing | done |
| 6  | OpenSubtitles hash | done |
| 7  | MediaInfo wrapper | done |
| 8  | TMDB metadata source | done |
| 9  | Identification pipeline | done |
| 10 | Template rendering and filename sanitization | done |
| 11 | Companion file classification and renaming | **todo** |
| 12 | File scanner and grouper | done |
| 13 | Pre-flight collision detector | **todo** |
| 14 | EventBus | done |
| 15 | Plugin loader | **todo** |
| 16 | File operations | done |
| 17 | Session tracking | done |
| 18 | Rich-based interactive import display | **todo** |
| 19 | Import service | done |
| 20 | Startup validation | done |
| 21 | Query service | **todo** |
| 22 | tapes check command | **todo** |
| 23 | tapes move command | **todo** |
| 24 | Wire import command | done |
| 25 | Wire query, stats, info, fields commands | **todo** |
| 26 | Wire modify command | **todo** |
| 27 | Wire move, check, log commands | **todo** |
| 28 | NFO sidecar plugin | **todo** |

89 tests passing. Pick up from Task 13.

---

## Phase 1: Project Scaffolding

### Task 1: Project setup

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `tapes/__init__.py`
- Create: `tapes/__main__.py`
- Create: `tests/__init__.py`
- Create: `tapes.toml.example`

**Step 1: Create `pyproject.toml`**

```toml
[project]
name = "tapes"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13",
    "guessit>=3.8",
    "pymediainfo>=6.1",
    "requests>=2.31",
    "pydantic>=2.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-cov",
    "responses",
]

[project.scripts]
tapes = "tapes.cli.main:app"

[project.entry-points."tapes.plugins"]
nfo = "tapes.plugins.builtin.nfo:NfoPlugin"
artwork = "tapes.plugins.builtin.artwork:ArtworkPlugin"
subtitles = "tapes.plugins.builtin.subtitles:SubtitlesPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: Create `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
dist/
*.egg-info/
.pytest_cache/
.coverage
*.db
*.db-shm
*.db-wal
```

**Step 3: Create `tapes/__init__.py`** (empty)

**Step 4: Create `tapes/__main__.py`**

```python
from tapes.cli.main import app

if __name__ == "__main__":
    app()
```

**Step 5: Create `tapes.toml.example`** — copy the full Configuration Reference section from the design doc.

**Step 6: Write a smoke test**

```python
# tests/test_smoke.py
def test_import():
    import tapes
```

Run: `pytest tests/test_smoke.py` — expected: PASS.

**Step 7: Commit**

```bash
git add .
git commit -m "feat: project scaffolding"
```

---

### Task 2: CLI skeleton

**Files:**
- Create: `tapes/cli/main.py`
- Create: `tapes/cli/commands/__init__.py`
- Create: `tapes/cli/commands/import_.py`
- Create: `tapes/cli/commands/move.py`
- Create: `tapes/cli/commands/check.py`
- Create: `tapes/cli/commands/modify.py`
- Create: `tapes/cli/commands/query.py`
- Create: `tapes/cli/commands/info.py`
- Create: `tapes/cli/commands/fields.py`
- Create: `tapes/cli/commands/stats.py`
- Create: `tapes/cli/commands/log.py`
- Create: `tests/test_cli.py`

**Step 1: Write test**

```python
# tests/test_cli.py
from typer.testing import CliRunner
from tapes.cli.main import app

runner = CliRunner()

def test_app_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

def test_import_help():
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output

def test_move_help():
    result = runner.invoke(app, ["move", "--help"])
    assert result.exit_code == 0

def test_modify_help():
    result = runner.invoke(app, ["modify", "--help"])
    assert result.exit_code == 0
```

**Step 2: Create `tapes/cli/main.py`**

```python
import typer
from tapes.cli.commands import import_, move, check, modify, query, info, fields, stats, log

app = typer.Typer(name="tapes", help="Movie and TV show file organiser.")

app.command("import")(import_.command)
app.command("move")(move.command)
app.command("check")(check.command)
app.command("modify")(modify.command)
app.command("query")(query.command)
app.command("info")(info.command)
app.command("fields")(fields.command)
app.command("stats")(stats.command)
app.command("log")(log.command)
```

**Step 3: Stub each command file.** Example for `import_.py`:

```python
# tapes/cli/commands/import_.py
import typer
from pathlib import Path
from typing import Optional

def command(
    path: Path = typer.Argument(..., help="Path to scan for media files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes."),
    interactive: bool = typer.Option(False, "--interactive", help="Force interactive for all groups."),
    no_db: bool = typer.Option(False, "--no-db", help="Identify and rename only, no DB writes."),
    mode: Optional[str] = typer.Option(None, "--mode", help="copy|move|link|hardlink"),
    confidence: Optional[float] = typer.Option(None, "--confidence", help="Override confidence threshold."),
):
    """Import media files from PATH."""
    typer.echo(f"import {path} (not yet implemented)")
```

Create analogous stubs for all other commands. `move` gets `--dry-run`. `modify` gets `--id` and `--no-move`. `log` gets `--full` and optional `session_id` argument.

**Step 4: Run tests** — expected: all PASS.

**Step 5: Commit**

```bash
git add .
git commit -m "feat: CLI skeleton with all command stubs"
```

---

## Phase 2: Config System

### Task 3: Config schema and loading

**Files:**
- Create: `tapes/config/schema.py`
- Create: `tapes/config/loader.py`
- Create: `tests/test_config/test_schema.py`
- Create: `tests/test_config/test_loader.py`

**Step 1: Write schema tests**

```python
# tests/test_config/test_schema.py
from tapes.config.schema import TapesConfig

def test_defaults():
    cfg = TapesConfig()
    assert cfg.import_.mode == "copy"
    assert cfg.import_.confidence_threshold == 0.9
    assert cfg.companions.move.subtitle is True
    assert cfg.companions.move.unknown is False

def test_invalid_mode():
    import pytest
    with pytest.raises(Exception):
        TapesConfig(import_={"mode": "invalid"})
```

**Step 2: Create `tapes/config/schema.py`**

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""

class ImportConfig(BaseModel):
    mode: Literal["copy", "move", "link", "hardlink"] = "copy"
    confidence_threshold: float = 0.9
    interactive: bool = False
    dry_run: bool = False

class MetadataConfig(BaseModel):
    movies: str = "tmdb"
    tv: str = "tmdb"
    tmdb_api_key: str = ""

class TemplatesConfig(BaseModel):
    movie: str = "{title} ({year})/{title} ({year}){ext}"
    tv: str = "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d} - {episode_title}{ext}"

class CompanionsMoveConfig(BaseModel):
    subtitle: bool = True
    artwork: bool = True
    nfo: bool = True
    sample: bool = False
    unknown: bool = False

class CompanionsConfig(BaseModel):
    subtitle: list[str] = ["*.srt", "*.ass", "*.vtt", "*.sub", "*.idx", "*.ssa"]
    artwork: list[str] = ["poster.jpg", "folder.jpg", "fanart.jpg", "banner.jpg", "thumb.jpg"]
    sample: list[str] = ["sample.*", "*-sample.*", "*sample*.*"]
    ignore: list[str] = ["*.url", "*.lnk", "Thumbs.db", ".DS_Store"]
    move: CompanionsMoveConfig = CompanionsMoveConfig()

class TapesConfig(BaseModel):
    library: LibraryConfig = LibraryConfig()
    import_: ImportConfig = ImportConfig()
    metadata: MetadataConfig = MetadataConfig()
    templates: TemplatesConfig = TemplatesConfig()
    companions: CompanionsConfig = CompanionsConfig()
    replace: dict[str, str] = {": ": " - ", "/": "-"}

    class Config:
        populate_by_name = True
```

**Step 3: Create `tapes/config/loader.py`**

```python
import tomllib
from pathlib import Path
from tapes.config.schema import TapesConfig

DEFAULT_PATHS = [
    Path("tapes.toml"),
    Path.home() / ".config" / "tapes" / "tapes.toml",
]

def load_config(path: Path | None = None) -> TapesConfig:
    if path is None:
        for candidate in DEFAULT_PATHS:
            if candidate.exists():
                path = candidate
                break

    if path is None or not path.exists():
        return TapesConfig()

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"Error in config file {path}:\n  {e}") from e

    # Rename 'import' → 'import_' for pydantic
    if "import" in data:
        data["import_"] = data.pop("import")

    return TapesConfig.model_validate(data)
```

**Step 4: Write loader tests** — test that: a valid TOML is parsed, an invalid TOML exits with a clear message, missing file returns defaults.

**Step 5: Run tests, commit.**

---

## Phase 3: Database

### Task 4: SQLite schema and repository

**Files:**
- Create: `tapes/db/schema.py`
- Create: `tapes/db/migrations/001_initial.py`
- Create: `tapes/db/repository.py`
- Create: `tests/test_db.py`

**Step 1: Write schema tests**

```python
# tests/test_db.py
import sqlite3, pytest
from tapes.db.schema import init_db, get_schema_version

def test_init_creates_tables(tmp_path):
    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(db_path)
    init_db(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "schema_version" in tables
    assert "items" in tables
    assert "sessions" in tables
    assert "operations" in tables
    assert "seasons" in tables

def test_schema_version(tmp_path):
    conn = sqlite3.connect(tmp_path / "library.db")
    init_db(conn)
    assert get_schema_version(conn) == 1
```

**Step 2: Create `tapes/db/schema.py`**

```python
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
```

**Step 3: Create `tapes/db/migrations/001_initial.py`**

```python
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
```

**Step 4: Create `tapes/db/repository.py`** — thin wrapper around sqlite3 with typed methods:

```python
import sqlite3
from dataclasses import dataclass
from pathlib import Path

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
        """Insert or update an item record. Returns the row id."""
        # ... implementation
        pass

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

def _row_to_item(row) -> ItemRecord:
    return ItemRecord(*row)
```

**Step 5: Write repository tests** — test find_by_path_stat (hit and miss), upsert_item, create_session, create_operation.

**Step 6: Run tests, commit.**

---

## Phase 4: Identification

### Task 5: Filename parsing

**Files:**
- Create: `tapes/identification/filename.py`
- Create: `tests/test_identification/test_filename.py`

**Step 1: Write tests**

```python
# tests/test_identification/test_filename.py
from tapes.identification.filename import parse_filename

def test_movie():
    r = parse_filename("Dune.2021.2160p.BluRay.x265.mkv")
    assert r["title"] == "Dune"
    assert r["year"] == 2021
    assert r["resolution"] == "2160p"
    assert r["source"] == "Blu-ray"
    assert r["codec"] == "H.265"

def test_tv_episode():
    r = parse_filename("The.Wire.S01E03.720p.mkv")
    assert r["show"] == "The Wire"
    assert r["season"] == 1
    assert r["episode"] == 3

def test_multi_episode_returns_list():
    r = parse_filename("The.Wire.S01E01E02.mkv")
    assert isinstance(r["episode"], list)
    assert r["episode"] == [1, 2]

def test_edition():
    r = parse_filename("Blade.Runner.1982.Directors.Cut.mkv")
    assert r.get("edition") is not None

def test_folder_name_as_hint(tmp_path):
    # Folder name used as additional context
    r = parse_filename("s01e01.mkv", folder_name="The Wire (2002)")
    assert r["show"] == "The Wire"
    assert r["year"] == 2002
```

**Step 2: Create `tapes/identification/filename.py`**

```python
from guessit import guessit

def parse_filename(filename: str, folder_name: str | None = None) -> dict:
    """
    Parse a filename using guessit, with optional folder name as additional context.
    Returns a dict of fields. 'episode' may be int or list[int] for multi-episode files.
    """
    result = dict(guessit(filename))

    # If guessit couldn't determine the title, try the folder name
    if not result.get("title") and folder_name:
        folder_result = dict(guessit(folder_name))
        result.setdefault("title", folder_result.get("title"))
        result.setdefault("year", folder_result.get("year"))

    return result
```

**Step 3: Run tests, commit.**

---

### Task 6: OpenSubtitles hash

**Files:**
- Create: `tapes/identification/osdb_hash.py`
- Create: `tests/test_identification/test_osdb_hash.py`

> Note: This task implements hash computation only. The API call to OpenSubtitles is deferred to post-v0.1. The hash is computed and stored for future use.

**Step 1: Write tests**

```python
# tests/test_identification/test_osdb_hash.py
from tapes.identification.osdb_hash import compute_hash
import tempfile, os

def test_hash_small_file(tmp_path):
    f = tmp_path / "test.mkv"
    f.write_bytes(b"\x00" * 1024)
    h = compute_hash(f)
    assert isinstance(h, str)
    assert len(h) == 16  # 64-bit hash as hex string

def test_hash_deterministic(tmp_path):
    f = tmp_path / "test.mkv"
    f.write_bytes(b"\xAB" * 65536 * 2)
    assert compute_hash(f) == compute_hash(f)
```

**Step 2: Create `tapes/identification/osdb_hash.py`**

```python
import struct
from pathlib import Path

CHUNK = 65536  # 64 KB

def compute_hash(path: Path) -> str:
    """
    Compute the OpenSubtitles movie hash.
    Hash = size + 64-bit checksum of first 64KB + last 64KB.
    Returns a 16-character hex string.
    """
    size = path.stat().st_size
    hash_value = size

    with open(path, "rb") as f:
        for chunk in (f.read(CHUNK), _read_last_chunk(f, size)):
            for word in struct.iter_unpack("<Q", chunk.ljust(CHUNK, b"\x00")):
                hash_value = (hash_value + word[0]) & 0xFFFFFFFFFFFFFFFF

    return format(hash_value, "016x")

def _read_last_chunk(f, size: int) -> bytes:
    f.seek(max(0, size - CHUNK))
    return f.read(CHUNK)
```

**Step 3: Run tests, commit.**

---

### Task 7: MediaInfo wrapper

**Files:**
- Create: `tapes/identification/mediainfo.py`
- Create: `tests/test_identification/test_mediainfo.py`

**Step 1: Write tests**

```python
# tests/test_identification/test_mediainfo.py
from unittest.mock import patch, MagicMock
from tapes.identification.mediainfo import parse_mediainfo

def test_returns_empty_when_unavailable(tmp_path):
    f = tmp_path / "test.mkv"
    f.write_bytes(b"fake")
    with patch("tapes.identification.mediainfo.MEDIAINFO_AVAILABLE", False):
        result = parse_mediainfo(f)
    assert result == {}

def test_extracts_fields():
    mock_track = MagicMock()
    mock_track.track_type = "Video"
    mock_track.codec_id = "V_MPEGH/ISO/HEVC"
    mock_track.width = 3840
    mock_track.height = 2160
    mock_track.hdr_format = "Dolby Vision"

    with patch("tapes.identification.mediainfo.MediaInfo") as MockMI:
        MockMI.parse.return_value.tracks = [mock_track]
        result = parse_mediainfo("fake.mkv")

    assert result["resolution"] == "2160p"
    assert result["hdr"] == 1
    assert result["codec"] is not None
```

**Step 2: Create `tapes/identification/mediainfo.py`**

```python
from pathlib import Path

try:
    from pymediainfo import MediaInfo
    # Verify the system library is actually available
    MediaInfo.parse.__doc__  # attribute access check
    MEDIAINFO_AVAILABLE = True
except Exception:
    MEDIAINFO_AVAILABLE = False

def parse_mediainfo(path) -> dict:
    """
    Extract technical metadata from a media file.
    Returns {} if pymediainfo is unavailable or the file cannot be parsed.
    MediaInfo values take precedence over guessit for technical fields.
    """
    if not MEDIAINFO_AVAILABLE:
        return {}

    try:
        info = MediaInfo.parse(str(path))
    except Exception:
        return {}

    result = {}
    for track in info.tracks:
        if track.track_type == "Video":
            result.update(_parse_video_track(track))
        elif track.track_type == "Audio" and "audio" not in result:
            result["audio"] = getattr(track, "commercial_name", None) or getattr(track, "format", None)
        elif track.track_type == "General":
            title = getattr(track, "title", None) or getattr(track, "movie_name", None)
            if title:
                result["embedded_title"] = title

    return result

def _parse_video_track(track) -> dict:
    out = {}
    width = getattr(track, "width", None)
    height = getattr(track, "height", None)
    if height:
        if height >= 2160:
            out["resolution"] = "2160p"
        elif height >= 1080:
            out["resolution"] = "1080p"
        elif height >= 720:
            out["resolution"] = "720p"
        else:
            out["resolution"] = f"{height}p"

    codec_id = getattr(track, "codec_id", None) or getattr(track, "format", None)
    if codec_id:
        out["codec"] = codec_id

    hdr = getattr(track, "hdr_format", None) or getattr(track, "transfer_characteristics", None)
    out["hdr"] = 1 if hdr else 0

    return out
```

**Step 3: Run tests, commit.**

---

### Task 8: TMDB metadata source

**Files:**
- Create: `tapes/metadata/base.py`
- Create: `tapes/metadata/tmdb.py`
- Create: `tests/test_metadata/test_tmdb.py`

**Step 1: Create `tapes/metadata/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SearchResult:
    tmdb_id: int
    title: str
    year: int | None
    media_type: str       # "movie" | "tv"
    confidence: float
    director: str | None = None
    genre: str | None = None
    show: str | None = None
    season: int | None = None
    episode: int | None = None
    episode_title: str | None = None

class MetadataSource(ABC):
    @abstractmethod
    def search(self, title: str, year: int | None, media_type: str) -> list[SearchResult]:
        ...

    @abstractmethod
    def get_by_id(self, tmdb_id: int, media_type: str) -> SearchResult | None:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return False if the source cannot be reached or is not configured."""
        ...
```

**Step 2: Write TMDB tests** — mock `requests.get` with `responses` library.

```python
# tests/test_metadata/test_tmdb.py
import responses as resp_lib
from tapes.metadata.tmdb import TMDBSource

@resp_lib.activate
def test_search_movie():
    resp_lib.add(
        resp_lib.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": [{"id": 438631, "title": "Dune", "release_date": "2021-09-15", "genre_ids": [878]}]},
    )
    resp_lib.add(
        resp_lib.GET,
        "https://api.themoviedb.org/3/movie/438631",
        json={"id": 438631, "title": "Dune", "release_date": "2021-09-15", "genres": [{"name": "Sci-Fi"}], "credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]}},
    )
    source = TMDBSource(api_key="testkey")
    results = source.search("Dune", 2021, "movie")
    assert len(results) >= 1
    assert results[0].tmdb_id == 438631
    assert results[0].title == "Dune"

@resp_lib.activate
def test_is_available_false_on_401():
    resp_lib.add(resp_lib.GET, "https://api.themoviedb.org/3/configuration", status=401)
    source = TMDBSource(api_key="bad_key")
    assert source.is_available() is False
```

**Step 3: Create `tapes/metadata/tmdb.py`**

Implement `TMDBSource(MetadataSource)` using `requests`. Confidence scoring per the design doc scoring table:
- Exact title + exact year → 0.90
- Exact title + year off by 1 → 0.75
- Exact title, no year → 0.70
- Fuzzy match (Levenshtein ratio > 0.85) + year → 0.65
- Fuzzy match, no year → 0.50

`is_available()` pings `/3/configuration` and returns `False` on 401 or network error.

**Step 4: Run tests, commit.**

---

### Task 9: Identification pipeline

**Files:**
- Create: `tapes/identification/pipeline.py`
- Create: `tapes/identification/nfo_scanner.py`
- Create: `tests/test_identification/test_pipeline.py`
- Create: `tests/test_identification/test_nfo_scanner.py`

> There is NO `xattr_cache.py`. DB lookup by (path, mtime, size) is step 1 of the pipeline.

**Step 1: Write NFO scanner tests**

```python
# tests/test_identification/test_nfo_scanner.py
from tapes.identification.nfo_scanner import scan_for_nfo_id
from pathlib import Path

def test_finds_tmdb_in_nfo(tmp_path):
    nfo = tmp_path / "movie.nfo"
    nfo.write_text('<movie><tmdbid>438631</tmdbid></movie>')
    result = scan_for_nfo_id(tmp_path / "movie.mkv")
    assert result == ("tmdb", 438631)

def test_walks_up_two_levels(tmp_path):
    show_dir = tmp_path / "The Wire"
    season_dir = show_dir / "Season 01"
    season_dir.mkdir(parents=True)
    nfo = show_dir / "tvshow.nfo"
    nfo.write_text('<tvshow><tmdbid>1438</tmdbid></tvshow>')
    result = scan_for_nfo_id(season_dir / "s01e01.mkv")
    assert result == ("tmdb", 1438)

def test_returns_none_when_absent(tmp_path):
    (tmp_path / "movie.mkv").touch()
    assert scan_for_nfo_id(tmp_path / "movie.mkv") is None
```

**Step 2: Create `tapes/identification/nfo_scanner.py`**

Parse XML NFO files for `<tmdbid>`, `<imdbid>`, `<uniqueid type="tmdb">`. Walk up to 2 directory levels for `tvshow.nfo`.

**Step 3: Write pipeline tests**

```python
# tests/test_identification/test_pipeline.py
from unittest.mock import MagicMock, patch
from tapes.identification.pipeline import IdentificationPipeline

def test_db_cache_hit_returns_immediately(tmp_path):
    repo = MagicMock()
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"\x00" * 100)
    cached = MagicMock()
    repo.find_by_path_stat.return_value = cached

    pipeline = IdentificationPipeline(repo=repo, metadata_source=MagicMock())
    result = pipeline.identify(f)

    assert result.item == cached
    assert result.source == "db_cache"
    repo.find_by_path_stat.assert_called_once()

def test_falls_through_to_interactive_when_low_confidence(tmp_path):
    repo = MagicMock()
    repo.find_by_path_stat.return_value = None
    f = tmp_path / "108-wow.mkv"
    f.write_bytes(b"\x00" * 100)

    metadata = MagicMock()
    metadata.is_available.return_value = True
    metadata.search.return_value = []  # no results

    pipeline = IdentificationPipeline(repo=repo, metadata_source=metadata, confidence_threshold=0.9)
    result = pipeline.identify(f)

    assert result.requires_interaction is True
    assert result.candidates == []
```

**Step 4: Create `tapes/identification/pipeline.py`**

```python
from dataclasses import dataclass, field
from pathlib import Path
from tapes.db.repository import Repository, ItemRecord
from tapes.metadata.base import MetadataSource, SearchResult
from tapes.identification.filename import parse_filename
from tapes.identification.osdb_hash import compute_hash
from tapes.identification.mediainfo import parse_mediainfo
from tapes.identification.nfo_scanner import scan_for_nfo_id

OSDB_HASH_CONFIDENCE = 0.97
NFO_ID_CONFIDENCE = 0.95

@dataclass
class IdentificationResult:
    item: ItemRecord | None = None
    candidates: list[SearchResult] = field(default_factory=list)
    file_info: dict = field(default_factory=dict)
    source: str | None = None
    requires_interaction: bool = False

class IdentificationPipeline:
    def __init__(self, repo: Repository, metadata_source: MetadataSource, confidence_threshold: float = 0.9):
        self._repo = repo
        self._meta = metadata_source
        self._threshold = confidence_threshold

    def identify(self, path: Path) -> IdentificationResult:
        stat = path.stat()

        # Step 1: DB cache
        cached = self._repo.find_by_path_stat(str(path), stat.st_mtime, stat.st_size)
        if cached:
            return IdentificationResult(item=cached, source="db_cache")

        file_info = {"path": str(path), "mtime": stat.st_mtime, "size": stat.st_size}

        # Step 2 & 3: NFO scan
        nfo_id = scan_for_nfo_id(path)
        if nfo_id:
            id_type, id_val = nfo_id
            result = self._meta.get_by_id(id_val, "movie")  # or tv — detect from nfo type
            if result:
                result.confidence = NFO_ID_CONFIDENCE
                return IdentificationResult(candidates=[result], file_info=file_info, source="nfo")

        # Step 4: guessit
        parsed = parse_filename(path.name, folder_name=path.parent.name)
        file_info.update(parsed)

        # Guard against multi-episode list from guessit
        if isinstance(file_info.get("episode"), list):
            file_info["episode"] = None  # flag for manual handling

        # Step 5: OSDB hash (computed; API call deferred to post-v0.1)
        osdb_hash = compute_hash(path)
        file_info["osdb_hash"] = osdb_hash

        # Step 6: MediaInfo
        media_fields = parse_mediainfo(path)
        file_info.update(media_fields)  # MediaInfo overrides guessit for technical fields

        # Step 7: TMDB query
        candidates = []
        if self._meta.is_available():
            title = file_info.get("title") or file_info.get("show") or ""
            year = file_info.get("year")
            media_type = "tv" if "season" in file_info else "movie"
            candidates = self._meta.search(title, year, media_type)

        # Step 8: Auto-accept or interactive fallback
        if candidates and candidates[0].confidence >= self._threshold:
            return IdentificationResult(candidates=candidates, file_info=file_info, source="filename")

        return IdentificationResult(
            candidates=candidates,
            file_info=file_info,
            requires_interaction=True,
        )
```

**Step 5: Run tests, commit.**

---

## Phase 5: Template Engine

### Task 10: Template rendering and filename sanitization

**Files:**
- Create: `tapes/templates/engine.py`
- Create: `tests/test_templates.py`

**Step 1: Write tests**

```python
# tests/test_templates.py
from tapes.templates.engine import render_template, sanitize_path

def test_basic_movie():
    result = render_template(
        "{title} ({year})/{title} ({year}){ext}",
        {"title": "Dune", "year": 2021, "ext": ".mkv"}
    )
    assert result == "Dune (2021)/Dune (2021).mkv"

def test_conditional_edition_present():
    result = render_template(
        "{title} ({year}){edition: - $}{ext}",
        {"title": "Dune", "year": 2021, "edition": "Director's Cut", "ext": ".mkv"}
    )
    assert result == "Dune (2021) - Director's Cut.mkv"

def test_conditional_edition_absent():
    result = render_template(
        "{title} ({year}){edition: - $}{ext}",
        {"title": "Dune", "year": 2021, "ext": ".mkv"}
    )
    assert result == "Dune (2021).mkv"

def test_missing_field_renders_empty():
    result = render_template("{title} ({year}){ext}", {"title": "Dune", "ext": ".mkv"})
    assert result == "Dune ().mkv"

def test_sanitize_colon():
    assert sanitize_path("Mission: Impossible.mkv") == "Mission - Impossible.mkv"

def test_sanitize_windows_reserved():
    assert "CON" not in sanitize_path("CON.mkv")

def test_sanitize_slash_in_title():
    assert "/" not in sanitize_path("AC/DC: Live.mkv")
```

**Step 2: Create `tapes/templates/engine.py`**

Parse `{field}` syntax with support for:
- `{field:format}` — standard Python format spec (e.g., `{season:02d}`)
- `{field: prefix$suffix}` — conditional: renders `prefix{value}suffix` when field is present and non-empty, empty string otherwise

Sanitize rendered paths per the design doc `[replace]` rules, plus Windows reserved name detection.

**Step 3: Run tests, commit.**

---

## Phase 6: Companion Files

### Task 11: Companion file classification and renaming

**Files:**
- Create: `tapes/companions/classifier.py`
- Create: `tests/test_companions.py`

**Step 1: Write tests**

```python
# tests/test_companions.py
from tapes.companions.classifier import classify_companions, CompanionFile, Category

def test_subtitle_detected(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "movie.en.srt").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    subs = [c for c in companions if c.category == Category.SUBTITLE]
    assert len(subs) == 1
    assert subs[0].path.name == "movie.en.srt"

def test_ignore_not_returned(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "movie.url").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    assert all(c.category != Category.IGNORE for c in companions)

def test_subdirectory_preserved(tmp_path):
    (tmp_path / "movie.mkv").touch()
    subs_dir = tmp_path / "Subs"
    subs_dir.mkdir()
    (subs_dir / "movie.nl.srt").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    assert any(c.path == subs_dir / "movie.nl.srt" for c in companions)

def test_subtitle_rename():
    from tapes.companions.classifier import rename_companion
    new_name = rename_companion("movie.en.srt", "Dune (2021)", Category.SUBTITLE)
    assert new_name == "Dune (2021).en.srt"
```

**Step 2: Create `tapes/companions/classifier.py`**

```python
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path

class Category(str, Enum):
    VIDEO = "video"
    SUBTITLE = "subtitle"
    ARTWORK = "artwork"
    NFO = "nfo"
    SAMPLE = "sample"
    IGNORE = "ignore"
    UNKNOWN = "unknown"

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts"}

DEFAULT_PATTERNS: dict[Category, list[str]] = {
    Category.SUBTITLE: ["*.srt", "*.ass", "*.vtt", "*.sub", "*.idx", "*.ssa"],
    Category.ARTWORK: ["poster.jpg", "folder.jpg", "fanart.jpg", "banner.jpg", "thumb.jpg"],
    Category.NFO: ["*.nfo", "*.xml"],
    Category.SAMPLE: ["sample.*", "*-sample.*", "*sample*.*"],
    Category.IGNORE: ["*.url", "*.lnk", "Thumbs.db", ".DS_Store"],
}

@dataclass
class CompanionFile:
    path: Path
    category: Category
    move_by_default: bool
    relative_to_video: Path  # path relative to video file's parent

def classify_companions(video_path: Path, config=None) -> list[CompanionFile]:
    """Return all companion files for a video, excluding the video itself and ignore-listed files."""
    patterns = DEFAULT_PATTERNS  # TODO: merge with config.companions patterns
    move_defaults = {
        Category.SUBTITLE: True, Category.ARTWORK: True,
        Category.NFO: True, Category.SAMPLE: False, Category.UNKNOWN: False,
    }

    parent = video_path.parent
    companions = []
    for f in parent.rglob("*"):
        if f == video_path or not f.is_file() or f.suffix.lower() in VIDEO_EXTENSIONS:
            continue
        cat = _categorize(f.name, patterns)
        if cat == Category.IGNORE:
            continue
        companions.append(CompanionFile(
            path=f,
            category=cat,
            move_by_default=move_defaults.get(cat, False),
            relative_to_video=f.relative_to(parent),
        ))
    return companions

def _categorize(filename: str, patterns: dict) -> Category:
    for cat, pats in patterns.items():
        if any(fnmatch(filename, p) for p in pats):
            return cat
    return Category.UNKNOWN

def rename_companion(original_name: str, dest_stem: str, category: Category) -> str:
    """Compute the renamed filename for a companion at the destination."""
    parts = original_name.split(".")
    if category == Category.SUBTITLE and len(parts) >= 3:
        # Preserve language + extension: movie.en.srt → dest_stem.en.srt
        lang_and_ext = ".".join(parts[-2:])
        return f"{dest_stem}.{lang_and_ext}"
    elif category == Category.NFO:
        return f"{dest_stem}.nfo"
    else:
        return original_name  # artwork and unknown: keep original name
```

**Step 3: Run tests, commit.**

---

## Phase 7: Discovery and Grouping

### Task 12: File scanner and grouper

**Files:**
- Create: `tapes/discovery/scanner.py`
- Create: `tapes/discovery/grouper.py`
- Create: `tests/test_discovery/test_scanner.py`
- Create: `tests/test_discovery/test_grouper.py`

**Step 1: Write scanner tests**

```python
# tests/test_discovery/test_scanner.py
from tapes.discovery.scanner import scan_media_files
from pathlib import Path

def test_finds_video_files(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "readme.txt").touch()
    found = scan_media_files(tmp_path)
    assert any(f.name == "movie.mkv" for f in found)
    assert not any(f.name == "readme.txt" for f in found)

def test_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "ep.mkv").touch()
    found = scan_media_files(tmp_path)
    assert any(f.name == "ep.mkv" for f in found)
```

**Step 2: Create `tapes/discovery/scanner.py`** — recursive glob for video extensions.

**Step 3: Create `tapes/discovery/grouper.py`** — group video files by directory. A directory whose files are all in the same show/season forms one group. Single movies are their own group. Return a list of `MediaGroup(directory, video_files)`.

**Step 4: Run tests, commit.**

---

## Phase 8: Collision Detection

### Task 13: Pre-flight collision detector

**Files:**
- Create: `tapes/importer/collision.py`
- Create: `tests/test_importer/test_collision.py`

**Step 1: Write tests**

```python
# tests/test_importer/test_collision.py
from tapes.importer.collision import detect_collisions, CollisionType

def test_template_collision_detected():
    planned = [
        {"source": "Dune.4K.mkv", "dest": "Dune (2021)/Dune (2021).mkv", "resolution": "2160p"},
        {"source": "Dune.1080p.mkv", "dest": "Dune (2021)/Dune (2021).mkv", "resolution": "1080p"},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert len(collisions) == 1
    assert collisions[0].type == CollisionType.TEMPLATE_ONLY
    assert len(collisions[0].files) == 2

def test_no_collision_when_unique():
    planned = [
        {"source": "Dune.mkv", "dest": "Dune (2021)/Dune (2021).mkv"},
        {"source": "Arrival.mkv", "dest": "Arrival (2016)/Arrival (2016).mkv"},
    ]
    assert detect_collisions(planned, existing_paths=set()) == []

def test_likely_duplicate_detected():
    planned = [
        {"source": "dune-2021.mkv", "dest": "Dune (2021)/Dune (2021).mkv",
         "resolution": "2160p", "hdr": 1, "size": 22_000_000_000},
        {"source": "Dune.2021.mkv", "dest": "Dune (2021)/Dune (2021).mkv",
         "resolution": "2160p", "hdr": 1, "size": 21_900_000_000},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert collisions[0].type == CollisionType.LIKELY_DUPLICATE
```

**Step 2: Create `tapes/importer/collision.py`**

```python
from dataclasses import dataclass, field
from enum import Enum

class CollisionType(str, Enum):
    TEMPLATE_ONLY = "template_only"   # same dest, files differ in metadata/tech
    LIKELY_DUPLICATE = "likely_duplicate"  # same dest AND same metadata + similar tech

@dataclass
class Collision:
    type: CollisionType
    dest: str
    files: list[dict]
    diff_fields: list[str] = field(default_factory=list)  # for TEMPLATE_ONLY

def detect_collisions(planned: list[dict], existing_paths: set[str]) -> list[Collision]:
    """
    planned: list of dicts with at least {"source", "dest"} plus any metadata fields.
    existing_paths: set of destination paths already in the library (from DB).
    """
    by_dest: dict[str, list[dict]] = {}
    for item in planned:
        by_dest.setdefault(item["dest"], []).append(item)

    collisions = []
    for dest, items in by_dest.items():
        if len(items) < 2 and dest not in existing_paths:
            continue
        if dest in existing_paths and len(items) == 1:
            # Single item collides with existing library file
            collisions.append(Collision(type=CollisionType.TEMPLATE_ONLY, dest=dest, files=items))
            continue
        if len(items) >= 2:
            diff = _find_diff_fields(items)
            col_type = CollisionType.LIKELY_DUPLICATE if not diff else CollisionType.TEMPLATE_ONLY
            collisions.append(Collision(type=col_type, dest=dest, files=items, diff_fields=diff))

    return collisions

_TECH_FIELDS = ["resolution", "hdr", "codec", "audio", "source", "size"]

def _find_diff_fields(items: list[dict]) -> list[str]:
    """Return fields that differ between items (candidates for disambiguation)."""
    diff = []
    for field in _TECH_FIELDS:
        values = {i.get(field) for i in items}
        if len(values) > 1:
            diff.append(field)
    return diff
```

**Step 3: Run tests, commit.**

---

## Phase 9: EventBus and Plugin Loader

### Task 14: EventBus

**Files:**
- Create: `tapes/events/bus.py`
- Create: `tests/test_events.py`

**Step 1: Write tests**

```python
# tests/test_events.py
from tapes.events.bus import EventBus

def test_listener_called():
    bus = EventBus()
    calls = []
    bus.on("test_event", lambda x: calls.append(x))
    bus.emit("test_event", x=42)
    assert calls == [42]

def test_buggy_listener_does_not_propagate(caplog):
    import logging
    bus = EventBus()
    bus.on("event", lambda: 1/0)
    bus.on("event", lambda: None)  # second listener still runs
    with caplog.at_level(logging.ERROR):
        bus.emit("event")
    assert "ZeroDivisionError" in caplog.text

def test_no_listeners_is_noop():
    bus = EventBus()
    bus.emit("no_listeners")  # should not raise
```

**Step 2: Create `tapes/events/bus.py`** — implement per the design doc (try/except per listener).

**Step 3: Run tests, commit.**

---

### Task 15: Plugin loader

**Files:**
- Create: `tapes/plugins/loader.py`
- Create: `tapes/plugins/builtin/__init__.py`
- Create: `tests/test_plugins/test_loader.py`

> Plugins are discovered via `importlib.metadata.entry_points(group="tapes.plugins")`.
> A plugin section is enabled when it appears in config with `enabled = true` (or equivalent).
> Known non-plugin top-level keys: `library`, `import`, `metadata`, `templates`, `replace`, `companions`.

**Step 1: Write tests** — mock entry points, verify only enabled plugins are loaded.

**Step 2: Create `tapes/plugins/loader.py`** per the design doc.

**Step 3: Run tests, commit.**

---

## Phase 10: File Operations and Session Tracking

### Task 16: File operations

**Files:**
- Create: `tapes/importer/file_ops.py`
- Create: `tests/test_importer/test_file_ops.py`

**Step 1: Write tests**

```python
# tests/test_importer/test_file_ops.py
import hashlib
from tapes.importer.file_ops import copy_verify, safe_rename, move_file

def test_copy_verify_success(tmp_path):
    src = tmp_path / "src.mkv"
    dst = tmp_path / "dst.mkv"
    src.write_bytes(b"hello world")
    copy_verify(src, dst)
    assert dst.exists()
    assert dst.read_bytes() == b"hello world"

def test_copy_verify_detects_corruption(tmp_path, monkeypatch):
    import shutil, pytest
    src = tmp_path / "src.mkv"
    dst = tmp_path / "dst.mkv"
    src.write_bytes(b"hello")
    # Simulate corruption by writing garbage after copy
    original_copy = shutil.copy2
    def corrupt_copy(s, d, **kw):
        original_copy(s, d, **kw)
        Path(d).write_bytes(b"corrupted")
    monkeypatch.setattr(shutil, "copy2", corrupt_copy)
    with pytest.raises(IOError, match="checksum"):
        copy_verify(src, dst)

def test_safe_rename_same_filesystem(tmp_path):
    src = tmp_path / "old.mkv"
    dst = tmp_path / "new.mkv"
    src.write_bytes(b"data")
    safe_rename(src, dst)
    assert dst.exists()
    assert not src.exists()
```

**Step 2: Create `tapes/importer/file_ops.py`**

```python
import hashlib, shutil
from pathlib import Path

def copy_verify(src: Path, dst: Path) -> None:
    """Copy src to dst, then verify SHA-256 checksum. Raises IOError on mismatch."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_hash = _sha256(src)
    shutil.copy2(src, dst)
    dst_hash = _sha256(dst)
    if src_hash != dst_hash:
        dst.unlink(missing_ok=True)
        raise IOError(f"Checksum mismatch after copy: {src} → {dst}")

def safe_rename(src: Path, dst: Path) -> None:
    """
    Rename a file. Uses os.rename (atomic on same filesystem).
    Falls back to copy_verify + delete for cross-filesystem moves.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.rename(dst)
    except OSError:
        # Cross-filesystem: fall back to copy-verify-delete
        copy_verify(src, dst)
        src.unlink()

def move_file(src: Path, dst: Path, verify: bool = True) -> None:
    """Move src to dst. verify=True forces copy-verify-delete even on same filesystem."""
    if verify:
        copy_verify(src, dst)
        src.unlink()
    else:
        safe_rename(src, dst)

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
```

**Step 3: Run tests, commit.**

---

### Task 17: Session tracking

**Files:**
- Create: `tapes/importer/session.py`
- Create: `tests/test_importer/test_session.py`

**Step 1: Write tests** — verify session create/update/resume detection.

```python
# tests/test_importer/test_session.py
import sqlite3
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.importer.session import ImportSession

def test_create_and_complete(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    init_db(conn)
    repo = Repository(conn)
    session = ImportSession.create(repo, source_path="/some/path")
    assert session.session_id is not None
    session.complete()
    rows = conn.execute("SELECT state FROM sessions WHERE id = ?", (session.session_id,)).fetchall()
    assert rows[0][0] == "completed"

def test_detects_in_progress(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    init_db(conn)
    repo = Repository(conn)
    s = ImportSession.create(repo, source_path="/path")
    pending = ImportSession.find_in_progress(repo)
    assert any(p["id"] == s.session_id for p in pending)
```

**Step 2: Create `tapes/importer/session.py`**

```python
from dataclasses import dataclass
from tapes.db.repository import Repository

@dataclass
class ImportSession:
    session_id: int
    repo: Repository

    @classmethod
    def create(cls, repo: Repository, source_path: str) -> "ImportSession":
        sid = repo.create_session(source_path)
        return cls(session_id=sid, repo=repo)

    @classmethod
    def find_in_progress(cls, repo: Repository) -> list[dict]:
        return repo.get_in_progress_sessions()

    def add_operation(self, source_path: str, op_type: str) -> int:
        return self.repo.create_operation(self.session_id, source_path, op_type)

    def update_operation(self, op_id: int, **kwargs) -> None:
        self.repo.update_operation(op_id, **kwargs)

    def complete(self) -> None:
        from datetime import datetime, timezone
        self.repo.update_session_state(
            self.session_id, "completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    def abort(self) -> None:
        self.repo.update_session_state(self.session_id, "aborted")
```

**Step 3: Run tests, commit.**

---

## Phase 11: Interactive UI

### Task 18: Rich-based interactive import display

**Files:**
- Create: `tapes/importer/interactive.py`
- Create: `tests/test_importer/test_interactive.py`

**Step 1: Write tests** — use `typer.testing.CliRunner` with mocked input.

```python
# tests/test_importer/test_interactive.py
from unittest.mock import patch
from tapes.importer.interactive import InteractivePrompt, PromptAction

def test_accept_on_enter_high_confidence():
    prompt = InteractivePrompt(candidates=[_candidate(0.86)], second_candidate_confidence=0.40)
    assert prompt.default_action == PromptAction.ACCEPT

def test_search_on_enter_low_confidence():
    prompt = InteractivePrompt(candidates=[_candidate(0.55)], second_candidate_confidence=0.50)
    assert prompt.default_action == PromptAction.SEARCH

def test_search_on_enter_no_match():
    prompt = InteractivePrompt(candidates=[], after_failed_search=False)
    assert prompt.default_action == PromptAction.SEARCH

def test_skip_on_enter_after_failed_search():
    prompt = InteractivePrompt(candidates=[], after_failed_search=True)
    assert prompt.default_action == PromptAction.SKIP

def _candidate(confidence):
    from unittest.mock import MagicMock
    c = MagicMock()
    c.confidence = confidence
    return c
```

**Step 2: Create `tapes/importer/interactive.py`**

Implement `InteractivePrompt` with `default_action` logic per the design doc table, plus `display()` method that uses rich to render the companion file list, match info, and context-sensitive prompt keys (highlighted default, dimmed others).

Implement the companion file checklist editor (`[e]` key) using `rich.prompt` or a simple loop.

**Step 3: Run tests, commit.**

---

## Phase 12: Import Service

### Task 19: Import service

**Files:**
- Create: `tapes/importer/service.py`
- Create: `tests/test_importer/test_service.py`

**Step 1: Write integration test**

```python
# tests/test_importer/test_service.py
from unittest.mock import MagicMock, patch
import sqlite3
from pathlib import Path
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.importer.service import ImportService

def test_import_dry_run_does_not_move_files(tmp_path):
    src = tmp_path / "Dune.2021.mkv"
    src.write_bytes(b"\x00" * 1000)
    library = tmp_path / "Library"

    conn = sqlite3.connect(tmp_path / "lib.db")
    init_db(conn)
    repo = Repository(conn)

    meta = MagicMock()
    meta.is_available.return_value = True
    meta.search.return_value = [_result("Dune", 2021, 0.95)]

    svc = ImportService(repo=repo, metadata_source=meta, config=_config(library, dry_run=True))
    summary = svc.import_path(tmp_path)

    assert not any(library.rglob("*.mkv"))  # no files moved
    assert summary["dry_run"] is True

def _result(title, year, conf):
    from tapes.metadata.base import SearchResult
    return SearchResult(tmdb_id=1, title=title, year=year, media_type="movie", confidence=conf)

def _config(library, dry_run=False):
    from tapes.config.schema import TapesConfig, LibraryConfig, ImportConfig
    return TapesConfig(
        library=LibraryConfig(movies=str(library)),
        import_=ImportConfig(dry_run=dry_run),
    )
```

**Step 2: Create `tapes/importer/service.py`**

The import service orchestrates the full pipeline:
1. Validate config (TMDB API key, library paths configured) — see Task 20
2. Scan and group files
3. For each group: identify → resolve interactively if needed → accept/skip
4. Pre-flight collision detection across all accepted items
5. Resolve collisions interactively
6. Execute file operations via `file_ops` + session tracking
7. Write DB records, emit events
8. Print/return summary

**Step 3: Run tests, commit.**

---

## Phase 13: Startup Validation

### Task 20: Startup validation

**Files:**
- Modify: `tapes/importer/service.py`
- Modify: `tapes/cli/main.py`
- Create: `tests/test_validation.py`

**Step 1: Write tests**

```python
# tests/test_validation.py
from tapes.config.schema import TapesConfig, MetadataConfig, LibraryConfig
from tapes.validation import validate_config, ConfigError
import pytest

def test_missing_tmdb_key_raises():
    cfg = TapesConfig(metadata=MetadataConfig(tmdb_api_key=""))
    with pytest.raises(ConfigError, match="TMDB_API_KEY"):
        validate_config(cfg)

def test_missing_library_path_raises():
    cfg = TapesConfig(
        metadata=MetadataConfig(tmdb_api_key="abc"),
        library=LibraryConfig(movies=""),
    )
    with pytest.raises(ConfigError, match="library.movies"):
        validate_config(cfg)
```

**Step 2: Create `tapes/validation.py`**

```python
import os
from tapes.config.schema import TapesConfig

class ConfigError(SystemExit):
    pass

def validate_config(cfg: TapesConfig) -> None:
    """Validate required config at startup. Raises ConfigError with a clear message."""
    api_key = cfg.metadata.tmdb_api_key or os.environ.get("TMDB_API_KEY", "")
    if not api_key:
        raise ConfigError(
            "TMDB API key not configured.\n"
            "  Set TMDB_API_KEY environment variable, or add to config:\n"
            "    [metadata]\n"
            "    tmdb_api_key = \"your-key-here\""
        )

    if not cfg.library.movies and not cfg.library.tv:
        raise ConfigError(
            "No library paths configured.\n"
            "  Add to config:\n"
            "    [library]\n"
            "    movies = \"~/Media/Movies\"\n"
            "    tv    = \"~/Media/TV\""
        )
```

**Step 3: Call `validate_config(cfg)` at the top of `ImportService.__init__` and in the `tapes move` command.**

**Step 4: Run tests, commit.**

---

## Phase 14: Library Services

### Task 21: Query service

**Files:**
- Create: `tapes/library/service.py`
- Create: `tests/test_library/test_service.py`

**Step 1: Write tests**

```python
# tests/test_library/test_service.py
import sqlite3
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.service import LibraryService

def test_query_by_director(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    init_db(conn)
    conn.execute("""INSERT INTO items (path, media_type, title, year, director, mtime, size, imported_at)
                    VALUES (?, ?, ?, ?, ?, 0, 0, datetime('now'))""",
                 ("/path/mulholland.mkv", "movie", "Mulholland Drive", 2001, "David Lynch"))
    conn.commit()
    svc = LibraryService(Repository(conn))
    results = svc.query('director:"David Lynch"')
    assert len(results) == 1
    assert results[0].title == "Mulholland Drive"

def test_query_year_range(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    init_db(conn)
    for y in [1999, 2001, 2005]:
        conn.execute("""INSERT INTO items (path, media_type, title, year, mtime, size, imported_at)
                        VALUES (?, 'movie', 'Film', ?, 0, 0, datetime('now'))""",
                     (f"/p/{y}.mkv", y))
    conn.commit()
    svc = LibraryService(Repository(conn))
    results = svc.query("year:>2000")
    assert all(r.year > 2000 for r in results)
    assert len(results) == 2
```

**Step 2: Create `tapes/library/service.py`**

Use `shlex.split` for tokenization to handle quoted strings correctly. Support:
- `field:value` — exact match
- `field:"quoted value"` — exact match with spaces
- `field:>value`, `field:<value` — range queries on numeric fields
- `missing:episodes show:"The Wire"` — special syntax

**Step 3: Run tests, commit.**

---

### Task 22: tapes check command

**Files:**
- Create: `tapes/library/check.py`
- Modify: `tapes/cli/commands/check.py`
- Create: `tests/test_library/test_check.py`

**Step 1: Write tests**

```python
def test_detects_missing_file(tmp_path):
    # Item in DB, file not on disk
    ...

def test_detects_orphan_video(tmp_path):
    # Video file in library root, not in DB (only video extensions)
    ...

def test_root_mismatch_matching(tmp_path):
    # Items in DB at old root, files exist at new root configured in config
    # Should match by TMDB ID + episode info
    ...
```

**Step 2: Create `tapes/library/check.py`**

Per the design doc spec for `tapes check`. Orphaned file detection considers video extensions only. Manual-import records (no TMDB ID) matched by title + year + media type as fallback.

**Step 3: Wire to CLI, run tests, commit.**

---

## Phase 15: Move Command

### Task 23: tapes move command

**Files:**
- Create: `tapes/library/mover.py`
- Modify: `tapes/cli/commands/move.py`
- Create: `tests/test_library/test_mover.py`

**Step 1: Write tests**

```python
def test_dry_run_shows_changes_without_moving(tmp_path):
    # Set up library with files at old template path
    # Change template in config
    # Run mover with dry_run=True
    # Assert files are still at old path, output shows planned changes
    ...

def test_no_op_when_paths_match(tmp_path):
    # Files already at template-correct paths → nothing to do
    ...

def test_missing_source_skips_and_continues(tmp_path):
    # One DB record points to non-existent file
    # Move should skip it, report it, and continue with other files
    ...

def test_companion_files_moved_alongside(tmp_path):
    # Video + subtitle at source
    # After move, both are at destination
    ...
```

**Step 2: Create `tapes/library/mover.py`**

Implement the 9-step sequence from the design doc. Steps 5 (pre-flight collision) and 8 (execute) use the existing `collision.py` and `file_ops.py` modules.

**Step 3: Wire to CLI, run tests, commit.**

---

## Phase 16: CLI Wiring

### Task 24: Wire import command

**Files:**
- Modify: `tapes/cli/commands/import_.py`
- Create: `tests/test_cli/test_import_integration.py`

Wire the `import` command to `ImportService`. Pass config, override flags (mode, confidence, dry_run, no_db, interactive). Handle the session-resume prompt at startup.

---

### Task 25: Wire query, stats, info, fields commands

**Files:**
- Modify: `tapes/cli/commands/query.py`
- Modify: `tapes/cli/commands/stats.py`
- Modify: `tapes/cli/commands/info.py`
- Modify: `tapes/cli/commands/fields.py`

- `query`: call `LibraryService.query()`, format results as a rich table
- `stats`: aggregate queries (count by media_type, total size, etc.)
- `info`: run pipeline on the given file (DB lookup first, then full pipeline); display fields as key-value pairs
- `fields`: list all available template fields with descriptions; show actual values when a file is given

---

### Task 26: Wire modify command

**Files:**
- Modify: `tapes/cli/commands/modify.py`
- Create: `tapes/library/modifier.py`
- Create: `tests/test_library/test_modifier.py`

Implement `tapes modify` per the design doc spec. Reuse the interactive search/accept flow from `interactive.py`. After update, re-render template, rename file (unless `--no-move`), emit `after_write`.

---

### Task 27: Wire move, check, log commands

**Files:**
- Modify: `tapes/cli/commands/move.py`
- Modify: `tapes/cli/commands/check.py`
- Modify: `tapes/cli/commands/log.py`

- `move`: call `Mover`. Add `tapes log --list` subcommand to show all sessions.
- `check`: call `CheckService`. Print findings grouped by type.
- `log`: query sessions/operations tables. Default: summary. `--full`: every operation. `--list`: list all sessions with id, date, status. Invalid session ID: clear error message.

---

## Phase 17: NFO Plugin

### Task 28: NFO sidecar plugin

**Files:**
- Create: `tapes/plugins/builtin/nfo.py`
- Create: `tests/test_plugins/test_nfo.py`

Write a minimal `NfoPlugin` that listens on `after_write` and generates a Kodi/Jellyfin-compatible NFO file alongside the video. Only activates when `[nfo] enabled = true`.

```python
# Example NFO for a movie:
# <movie>
#   <title>Dune</title>
#   <year>2021</year>
#   <tmdbid>438631</tmdbid>
# </movie>
```

---

## Summary

| Phase | Tasks | Key deliverable |
|---|---|---|
| 1 | 1-2 | Project + CLI skeleton |
| 2 | 3 | Config system |
| 3 | 4 | DB schema (all 5 tables) |
| 4 | 5-9 | Identification pipeline (no xattr) |
| 5 | 10 | Template engine + sanitization |
| 6 | 11 | Companion file classification + renaming |
| 7 | 12 | Discovery + grouping |
| 8 | 13 | Pre-flight collision detection |
| 9 | 14-15 | EventBus + plugin loader |
| 10 | 16-17 | File ops + session tracking |
| 11 | 18 | Interactive UI (rich, context-sensitive defaults) |
| 12 | 19 | Import service (full pipeline) |
| 13 | 20 | Startup validation |
| 14 | 21-22 | Query service + tapes check |
| 15 | 23 | tapes move |
| 16 | 24-27 | CLI wiring for all commands |
| 17 | 28 | NFO plugin |

**Total: 28 tasks.** All deferred features (scrub, convert, OpenSubtitles API, artwork, subtitles plugins) are excluded from this plan and can be added in later iterations.
