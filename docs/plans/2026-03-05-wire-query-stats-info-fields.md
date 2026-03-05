# Wire query, stats, info, fields Commands — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the four remaining read-only CLI commands that let users query, inspect, and explore their library.

**Architecture:** Each command follows the same setup pattern (load config, open DB, create Repository). `query` and `stats` operate on DB items via `LibraryService`/`Repository`. `info` looks up a file in DB or runs the identification pipeline. `fields` lists template fields or shows values for a file.

**Tech Stack:** typer, rich (Table, Console), sqlite3, existing LibraryService/Repository/IdentificationPipeline

---

### Task 1: Wire the `query` command

**Files:**
- Modify: `tapes/cli/commands/query.py`
- Test: `tests/test_cli/test_query_cmd.py`

**Step 1: Write the test**

Create `tests/test_cli/__init__.py` and the test file:

```python
# tests/test_cli/__init__.py
# (empty)
```

```python
# tests/test_cli/test_query_cmd.py
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
        # Should only show 1 result

    def test_query_no_db(self, tmp_path, monkeypatch):
        toml = tmp_path / "tapes.toml"
        toml.write_text('[library]\ndb_path = "nonexistent.db"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["query", "title:Dune"])
        assert result.exit_code == 0
        assert "No database" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli/test_query_cmd.py -v`
Expected: FAIL (stub just prints placeholder)

**Step 3: Implement the command**

```python
# tapes/cli/commands/query.py
import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.service import LibraryService

console = Console()


def command(
    query_str: str = typer.Argument(..., metavar="QUERY", help="Query string, e.g. 'genre:thriller year:>2010'."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Maximum results to show."),
):
    """Query the library with structured search expressions."""
    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)
    svc = LibraryService(repo)

    items = svc.query(query_str)
    if limit is not None:
        items = items[:limit]

    if not items:
        console.print("[yellow]No results.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"{len(items)} result(s)")
    table.add_column("Title", style="bold")
    table.add_column("Year")
    table.add_column("Type")
    table.add_column("Show")
    table.add_column("S/E")
    table.add_column("Resolution")
    table.add_column("Codec")
    table.add_column("Path", style="dim")

    for item in items:
        se = ""
        if item.season is not None:
            se = f"S{item.season:02d}"
            if item.episode is not None:
                se += f"E{item.episode:02d}"
        table.add_row(
            item.title or "",
            str(item.year) if item.year else "",
            item.media_type,
            item.show or "",
            se,
            item.resolution or "",
            item.codec or "",
            item.path,
        )

    console.print(table)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli/test_query_cmd.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli/ tapes/cli/commands/query.py
git commit -m "feat: wire query command with rich table output"
```

---

### Task 2: Wire the `stats` command

**Files:**
- Modify: `tapes/cli/commands/stats.py`
- Test: `tests/test_cli/test_stats_cmd.py`

**Step 1: Write the test**

```python
# tests/test_cli/test_stats_cmd.py
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
        """INSERT INTO items (path, media_type, title, year, codec, resolution, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, 5000000000, datetime('now'))""",
        ("/movies/dune.mkv", "movie", "Dune", 2021, "hevc", "2160p"),
    )
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, codec, resolution,
           show, season, episode, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1000000000, datetime('now'))""",
        ("/tv/wire/s01e01.mkv", "tv", "The Target", 2002, "h264", "1080p", "The Wire", 1, 1),
    )
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, codec, resolution,
           show, season, episode, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1000000000, datetime('now'))""",
        ("/tv/wire/s01e02.mkv", "tv", "The Detail", 2002, "h264", "1080p", "The Wire", 1, 2),
    )
    conn.commit()
    conn.close()

    toml = tmp_path / "tapes.toml"
    toml.write_text(f'[library]\ndb_path = "{db_path}"\nmovies = "/movies"\ntv = "/tv"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestStatsCommand:
    def test_stats_shows_totals(self, db_with_items):
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "3" in result.output  # total items

    def test_stats_shows_media_types(self, db_with_items):
        result = runner.invoke(app, ["stats"])
        assert "movie" in result.output.lower()
        assert "tv" in result.output.lower()

    def test_stats_shows_codecs(self, db_with_items):
        result = runner.invoke(app, ["stats"])
        assert "hevc" in result.output
        assert "h264" in result.output

    def test_stats_no_db(self, tmp_path, monkeypatch):
        toml = tmp_path / "tapes.toml"
        toml.write_text('[library]\ndb_path = "nonexistent.db"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No database" in result.output

    def test_stats_empty_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "library.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.close()

        toml = tmp_path / "tapes.toml"
        toml.write_text(f'[library]\ndb_path = "{db_path}"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower() or "0" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli/test_stats_cmd.py -v`
Expected: FAIL

**Step 3: Implement the command**

```python
# tapes/cli/commands/stats.py
import sqlite3
from collections import Counter
from pathlib import Path

import typer
from rich.console import Console

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository

console = Console()


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def command():
    """Show library statistics."""
    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    items = repo.get_all_items()
    if not items:
        console.print("[yellow]Library is empty.[/yellow]")
        raise typer.Exit(0)

    total = len(items)
    type_counts = Counter(i.media_type for i in items)
    codec_counts = Counter(i.codec for i in items if i.codec)
    res_counts = Counter(i.resolution for i in items if i.resolution)
    total_size = sum(i.size for i in items)

    # TV details
    tv_items = [i for i in items if i.media_type == "tv"]
    shows = {i.show for i in tv_items if i.show}
    seasons = {(i.show, i.season) for i in tv_items if i.show and i.season is not None}

    console.print("[bold]Library Statistics[/bold]\n")

    console.print(f"  Total items:  {total}")
    for mt, count in type_counts.most_common():
        extra = ""
        if mt == "tv":
            extra = f"  ({len(shows)} show(s), {len(seasons)} season(s))"
        console.print(f"  {mt:12s}   {count}{extra}")

    console.print(f"\n  Total size:   {_human_size(total_size)}")

    if codec_counts:
        top_codecs = ", ".join(f"{c} ({n})" for c, n in codec_counts.most_common(5))
        console.print(f"  Codecs:       {top_codecs}")

    if res_counts:
        top_res = ", ".join(f"{r} ({n})" for r, n in res_counts.most_common(5))
        console.print(f"  Resolutions:  {top_res}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli/test_stats_cmd.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/cli/commands/stats.py tests/test_cli/test_stats_cmd.py
git commit -m "feat: wire stats command with library aggregates"
```

---

### Task 3: Wire the `info` command

**Files:**
- Modify: `tapes/cli/commands/info.py`
- Test: `tests/test_cli/test_info_cmd.py`

**Step 1: Write the test**

```python
# tests/test_cli/test_info_cmd.py
import sqlite3
import pytest
from typer.testing import CliRunner
from tapes.cli.main import app
from tapes.db.schema import init_db

runner = CliRunner()


@pytest.fixture
def db_with_file(tmp_path, monkeypatch):
    video = tmp_path / "dune.mkv"
    video.write_bytes(b"\x00" * 100)
    stat = video.stat()

    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """INSERT INTO items (path, media_type, title, year, director, genre,
           codec, resolution, hdr, confidence, match_source, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (str(video), "movie", "Dune", 2021, "Denis Villeneuve", "Sci-Fi",
         "hevc", "2160p", 0, 0.95, "filename", stat.st_mtime, stat.st_size),
    )
    conn.commit()
    conn.close()

    toml = tmp_path / "tapes.toml"
    toml.write_text(f'[library]\ndb_path = "{db_path}"\nmovies = "/movies"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestInfoCommand:
    def test_info_from_db(self, db_with_file):
        video = db_with_file / "dune.mkv"
        result = runner.invoke(app, ["info", str(video)])
        assert result.exit_code == 0
        assert "Dune" in result.output
        assert "2021" in result.output
        assert "hevc" in result.output

    def test_info_file_not_found(self, db_with_file):
        result = runner.invoke(app, ["info", "/nonexistent/file.mkv"])
        assert result.exit_code != 0 or "not found" in result.output.lower() or "error" in result.output.lower()

    def test_info_no_db(self, tmp_path, monkeypatch):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"\x00" * 100)
        toml = tmp_path / "tapes.toml"
        toml.write_text('[library]\ndb_path = "nonexistent.db"\n')
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["info", str(video)])
        assert result.exit_code == 0
        assert "No database" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli/test_info_cmd.py -v`
Expected: FAIL

**Step 3: Implement the command**

```python
# tapes/cli/commands/info.py
import sqlite3
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository, ItemRecord

console = Console()

_DISPLAY_FIELDS = [
    ("Path", "path"),
    ("Media type", "media_type"),
    ("TMDB ID", "tmdb_id"),
    ("Title", "title"),
    ("Year", "year"),
    ("Show", "show"),
    ("Season", "season"),
    ("Episode", "episode"),
    ("Episode title", "episode_title"),
    ("Director", "director"),
    ("Genre", "genre"),
    ("Edition", "edition"),
    ("Codec", "codec"),
    ("Resolution", "resolution"),
    ("Audio", "audio"),
    ("HDR", "hdr"),
    ("Match source", "match_source"),
    ("Confidence", "confidence"),
]


def _format_value(field: str, value) -> str:
    if value is None:
        return "-"
    if field == "hdr":
        return "yes" if value else "no"
    if field == "confidence" and isinstance(value, float):
        return f"{value:.0%}"
    return str(value)


def _print_item(item: ItemRecord) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    for label, field in _DISPLAY_FIELDS:
        value = getattr(item, field)
        table.add_row(label, _format_value(field, value))
    console.print(table)


def command(
    path: Path = typer.Argument(..., help="File to show info for."),
):
    """Show identified metadata for a file (runs pipeline if not in DB)."""
    path = path.resolve()

    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    stat = path.stat()
    item = repo.find_by_path_stat(str(path), stat.st_mtime, stat.st_size)

    if item:
        _print_item(item)
        return

    # Not in DB - try path-only lookup (file may have been modified)
    items = repo.query_items("path = ?", [str(path)])
    if items:
        _print_item(items[0])
        return

    console.print(f"[yellow]File not in library: {path}[/yellow]")
    console.print("Run [bold]tapes import[/bold] to add it.")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli/test_info_cmd.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/cli/commands/info.py tests/test_cli/test_info_cmd.py
git commit -m "feat: wire info command with DB lookup and key-value display"
```

---

### Task 4: Wire the `fields` command

**Files:**
- Modify: `tapes/cli/commands/fields.py`
- Test: `tests/test_cli/test_fields_cmd.py`

**Step 1: Write the test**

```python
# tests/test_cli/test_fields_cmd.py
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
    def test_fields_for_file_in_db(self, tmp_path, monkeypatch):
        video = tmp_path / "dune.mkv"
        video.write_bytes(b"\x00" * 100)
        stat = video.stat()

        db_path = tmp_path / "library.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute(
            """INSERT INTO items (path, media_type, title, year, director,
               codec, resolution, mtime, size, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (str(video), "movie", "Dune", 2021, "Denis Villeneuve",
             "hevc", "2160p", stat.st_mtime, stat.st_size),
        )
        conn.commit()
        conn.close()

        toml = tmp_path / "tapes.toml"
        toml.write_text(f'[library]\ndb_path = "{db_path}"\n')
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["fields", str(video)])
        assert result.exit_code == 0
        assert "Dune" in result.output
        assert "2021" in result.output
        assert ".mkv" in result.output  # ext field
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli/test_fields_cmd.py -v`
Expected: FAIL

**Step 3: Implement the command**

```python
# tapes/cli/commands/fields.py
import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tapes.config.loader import load_config
from tapes.db.schema import init_db
from tapes.db.repository import Repository

console = Console()

_FIELD_DESCRIPTIONS = [
    ("title", "Movie or episode title"),
    ("year", "Release year"),
    ("show", "TV show name (TV only)"),
    ("season", "Season number (TV only)"),
    ("episode", "Episode number (TV only)"),
    ("episode_title", "Episode title (TV only)"),
    ("director", "Primary director"),
    ("genre", "Genres from TMDB"),
    ("edition", "Edition (Director's Cut, Extended, etc.)"),
    ("codec", "Video codec (h264, hevc, vp9)"),
    ("resolution", "Video resolution (720p, 1080p, 2160p)"),
    ("audio", "Audio codec/language"),
    ("hdr", "HDR metadata present (0 or 1)"),
    ("media_type", "movie or tv"),
    ("ext", "File extension (.mkv, .mp4, etc.)"),
]


def command(
    path: Optional[Path] = typer.Argument(None, help="File to show available fields for."),
):
    """List all template fields available (optionally for a specific file)."""
    if path is None:
        _list_fields()
        return

    _show_fields_for_file(path.resolve())


def _list_fields() -> None:
    table = Table(title="Template Fields")
    table.add_column("Field", style="bold")
    table.add_column("Description")
    for name, desc in _FIELD_DESCRIPTIONS:
        table.add_row(name, desc)
    console.print(table)


def _show_fields_for_file(path: Path) -> None:
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    cfg = load_config()
    db_path = Path(cfg.library.db_path).expanduser()
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    stat = path.stat()
    item = repo.find_by_path_stat(str(path), stat.st_mtime, stat.st_size)
    if not item:
        items = repo.query_items("path = ?", [str(path)])
        item = items[0] if items else None

    if not item:
        console.print(f"[yellow]File not in library: {path}[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Fields for: {path.name}", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()

    field_names = [
        "title", "year", "show", "season", "episode", "episode_title",
        "director", "genre", "edition", "codec", "resolution", "audio",
        "hdr", "media_type",
    ]
    for name in field_names:
        value = getattr(item, name, None)
        if name == "hdr":
            value = "yes" if value else "no"
        table.add_row(name, str(value) if value is not None else "-")

    # Computed: ext
    table.add_row("ext", path.suffix)

    console.print(table)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli/test_fields_cmd.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/cli/commands/fields.py tests/test_cli/test_fields_cmd.py
git commit -m "feat: wire fields command with template field listing"
```

---

### Task 5: Run full test suite and final commit

**Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (existing 190 + new tests)

**Step 2: Verify CLI works end-to-end**

Run: `uv run tapes query --help && uv run tapes stats --help && uv run tapes info --help && uv run tapes fields --help`
Expected: Help text for each command

**Step 3: Update CLAUDE.md task table**

Change Task 25 status from `**next**` to `done`. Set Task 26 as `**next**`.

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: mark Task 25 as done"
```
