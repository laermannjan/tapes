# E2E Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 50 end-to-end tests covering the full import pipeline -- real
filenames through guessit, mocked TMDB HTTP, template rendering, file ops, and
DB -- across 5 test files.

**Architecture:** Each test creates real files on disk, mocks only TMDB HTTP
(via `responses` library), then calls `ImportService.import_path()`. Everything
else -- guessit, scoring, templates, file ops, SQLite -- runs for real. Shared
fixtures and TMDB mock helpers live in `conftest.py` and `tmdb_fixtures.py`.

**Tech Stack:** pytest, `responses` library, SQLite in-memory, `tmp_path`
fixture, `os.urandom` for file content.

**Design doc:** `docs/plans/2026-03-05-e2e-tests.md`

---

## Parallelization structure

Tasks 1 and 2 are **shared infrastructure** -- must be completed first.
Tasks 3-7 are **independent** and can be implemented in parallel by separate
subagents. Each produces one test file with no cross-file dependencies.

```
Task 1: conftest.py (fixtures)  ─┐
Task 2: tmdb_fixtures.py        ─┤
                                  ├──> Task 3: test_movie_import.py      (parallel)
                                  ├──> Task 4: test_tv_import.py         (parallel)
                                  ├──> Task 5: test_directory_structures.py (parallel)
                                  ├──> Task 6: test_companions.py        (parallel)
                                  └──> Task 7: test_edge_cases.py        (parallel)
```

---

## Reference: key imports and API

Every test file will need these imports. Listed here once to avoid repetition.

```python
import os
import sqlite3
import pytest
import responses

from tapes.config.schema import TapesConfig, LibraryConfig, ImportConfig, TemplatesConfig
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.metadata.tmdb import TMDBSource, BASE_URL
from tapes.importer.service import ImportService
```

### How the pipeline works (for implementors)

1. `ImportService.import_path(path)` calls `scan_media_files(path)` to find
   video files (extensions: `.mkv`, `.mp4`, `.avi`, `.mov`, `.m4v`, `.ts`,
   `.m2ts`, `.wmv`, `.flv`). Files matching the sample pattern in their stem
   are excluded.

2. Each video goes through `IdentificationPipeline.identify(path)`:
   - DB cache lookup (path + mtime + size)
   - NFO scan (looks for `*.nfo` in same dir and up to 2 parents)
   - `parse_filename()` via guessit -- extracts title, year, season, episode, etc.
   - Multi-episode guard: if `episode` is a list, forces `requires_interaction=True`
   - OSDB hash computation (runs on file bytes)
   - MediaInfo (degrades gracefully if binary not present)
   - TMDB search via HTTP -- **this is what we mock**
   - Confidence scoring: `jaro_winkler_similarity(normalized_query, normalized_result) * year_factor`
   - If top candidate confidence >= threshold: auto-accept
   - Otherwise: `requires_interaction=True`

3. In non-interactive mode (default), `requires_interaction=True` means the file
   is skipped (added to `summary.unmatched`, `summary.skipped += 1`).

4. Auto-accepted files get: template rendering -> file operation -> DB write.

5. `TMDBSource.search()` calls `is_available()` first (hits `/configuration`
   endpoint). If unavailable, returns empty candidates. Then hits
   `/search/movie` or `/search/tv`, then `/movie/{id}` or `/tv/{id}` for each
   result (up to 5). **Every test must mock all endpoints that will be hit.**

6. The `is_available()` result is cached on the `TMDBSource` instance. To avoid
   needing to mock `/configuration` in every test, the conftest fixture
   pre-sets `meta._available = True`.

### TMDB mock pattern

For a movie search, these endpoints are called in order:
```
GET /3/search/movie?query=<title>          -> search results JSON
GET /3/movie/<tmdb_id>?append_to_response=credits  -> detail JSON (per result)
```

For TV:
```
GET /3/search/tv?query=<title>             -> search results JSON
GET /3/tv/<tmdb_id>?append_to_response=credits     -> detail JSON (per result)
```

For NFO-based identification (get_by_id):
```
GET /3/movie/<tmdb_id>?append_to_response=credits  -> detail JSON
```
(No search endpoint hit.)

For `is_available()`:
```
GET /3/configuration                        -> any 200 response
```

---

## Task 1: Shared fixtures (`conftest.py`)

**Files:**
- Create: `tests/test_e2e/__init__.py`
- Create: `tests/test_e2e/conftest.py`

**What to build:**

```python
# tests/test_e2e/__init__.py
# (empty file)
```

```python
# tests/test_e2e/conftest.py
import os
import sqlite3

import pytest

from tapes.config.schema import (
    TapesConfig,
    LibraryConfig,
    ImportConfig,
    TemplatesConfig,
)
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.metadata.tmdb import TMDBSource
from tapes.importer.service import ImportService


@pytest.fixture
def library(tmp_path):
    """Create movie and TV library directories under tmp_path."""
    movies = tmp_path / "Movies"
    tv = tmp_path / "TV"
    movies.mkdir()
    tv.mkdir()
    return {"movies": movies, "tv": tv, "root": tmp_path}


@pytest.fixture
def source_dir(tmp_path):
    """Create a source directory for files to import."""
    src = tmp_path / "downloads"
    src.mkdir()
    return src


@pytest.fixture
def repo():
    """In-memory SQLite repository."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return Repository(conn)


@pytest.fixture
def make_config(library):
    """Factory: build a TapesConfig with sensible E2E defaults.

    The default movie template is ``{title} ({year})/{title} ({year}){ext}``.
    The default TV template is
    ``{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}{episode_title: - $}{ext}``.
    """

    def _make(
        mode="copy",
        threshold=0.9,
        dry_run=False,
        no_db=False,
        interactive=False,
        movie_template=None,
        tv_template=None,
    ):
        return TapesConfig(
            library=LibraryConfig(
                movies=str(library["movies"]),
                tv=str(library["tv"]),
            ),
            import_=ImportConfig(
                mode=mode,
                confidence_threshold=threshold,
                dry_run=dry_run,
                no_db=no_db,
                interactive=interactive,
            ),
            templates=TemplatesConfig(
                movie=movie_template or "{title} ({year})/{title} ({year}){ext}",
                tv=tv_template
                or "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}{episode_title: - $}{ext}",
            ),
        )

    return _make


@pytest.fixture
def make_service(repo, make_config):
    """Factory: build an ImportService wired to the in-memory repo.

    Returns ``(service, repo)`` so tests can query the DB afterward.
    The TMDBSource instance has ``_available`` pre-set to ``True`` so that
    ``is_available()`` never hits the network.
    """

    def _make(**config_overrides):
        cfg = make_config(**config_overrides)
        meta = TMDBSource(token="fake-token")
        meta._available = True  # skip /configuration check
        service = ImportService(
            repo=repo, metadata_source=meta, config=cfg
        )
        return service, repo

    return _make


# ---------------------------------------------------------------------------
# Helpers (importable by test files via conftest auto-discovery)
# ---------------------------------------------------------------------------


def make_video(directory, name, size=1024):
    """Create a dummy video file with random bytes.

    Creates parent directories as needed. Returns the Path.
    """
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(size))
    return path


def make_nfo(directory, name, tmdb_id, root_tag="movie"):
    """Create an NFO file containing a TMDB ID.

    Args:
        directory: Parent directory.
        name: Filename (e.g. ``movie.nfo`` or ``tvshow.nfo``).
        tmdb_id: The TMDB numeric ID.
        root_tag: XML root element name (``movie`` or ``tvshow``).
    """
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<{root_tag}><tmdbid>{tmdb_id}</tmdbid></{root_tag}>"
    )
    return path


def assert_imported(library_dir, rel_path, *, source=None, mode="copy"):
    """Assert a file was imported to the expected library path.

    Args:
        library_dir: The library root (e.g. ``library["movies"]``).
        rel_path: Expected path relative to library root.
        source: Optional source Path to check existence based on mode.
        mode: Import mode -- determines source file expectations.
    """
    dest = library_dir / rel_path
    assert dest.exists(), f"Expected {dest} to exist"
    if source and mode == "copy":
        assert source.exists(), "Source should still exist in copy mode"
    elif source and mode == "move":
        assert not source.exists(), "Source should be deleted in move mode"
    elif source and mode == "link":
        assert dest.is_symlink(), "Dest should be a symlink in link mode"
        assert source.exists(), "Source should still exist in link mode"
    elif source and mode == "hardlink":
        assert dest.stat().st_ino == source.stat().st_ino, "Should share inode"
    return dest


def assert_db_record(repo, *, count=None, **field_checks):
    """Assert DB records match expectations.

    Args:
        repo: Repository instance.
        count: If set, assert exactly this many records exist.
        **field_checks: Field name/value pairs. Checks the first record
            that matches all provided fields. Use ``confidence__gte`` for
            ``>=`` checks.
    """
    items = repo.get_all_items()
    if count is not None:
        assert len(items) == count, f"Expected {count} DB records, got {len(items)}"
    if not field_checks:
        return items

    gte_checks = {}
    eq_checks = {}
    for k, v in field_checks.items():
        if k.endswith("__gte"):
            gte_checks[k.removesuffix("__gte")] = v
        else:
            eq_checks[k] = v

    for item in items:
        match = True
        for field, expected in eq_checks.items():
            if getattr(item, field, None) != expected:
                match = False
                break
        if not match:
            continue
        for field, minimum in gte_checks.items():
            if getattr(item, field, None) is None or getattr(item, field) < minimum:
                match = False
                break
        if match:
            return item

    field_desc = ", ".join(f"{k}={v}" for k, v in field_checks.items())
    item_desc = "\n  ".join(str(vars(i)) for i in items)
    raise AssertionError(
        f"No DB record matching {field_desc}.\nRecords:\n  {item_desc}"
    )
```

**Verify:**

```bash
uv run pytest tests/test_e2e/ --collect-only
```

Expected: no errors, no tests collected yet (only fixtures).

**Commit:** `test: add E2E test fixtures and helpers`

---

## Task 2: TMDB response fixtures (`tmdb_fixtures.py`)

**Files:**
- Create: `tests/test_e2e/tmdb_fixtures.py`

**What to build:**

A module with canned TMDB API response data and a helper function to register
`responses` mocks. Each fixture mirrors the real TMDB API v3 response shape.

```python
# tests/test_e2e/tmdb_fixtures.py
"""Canned TMDB API responses for E2E tests.

Each entry is a dict with ``search`` and ``detail`` keys matching the real
TMDB v3 API JSON shape. Use ``mock_tmdb()`` to register them as HTTP mocks.
"""

import responses as resp_lib

BASE_URL = "https://api.themoviedb.org/3"

# ---- Movie fixtures -------------------------------------------------------

DUNE_2021 = {
    "search": {
        "results": [
            {
                "id": 438631,
                "title": "Dune",
                "release_date": "2021-09-15",
                "genre_ids": [878, 12],
            }
        ]
    },
    "detail": {
        "id": 438631,
        "title": "Dune",
        "release_date": "2021-09-15",
        "genres": [{"name": "Science Fiction"}, {"name": "Adventure"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Denis Villeneuve"}]
        },
    },
}

THE_MATRIX_1999 = {
    "search": {
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-30",
                "genre_ids": [28, 878],
            }
        ]
    },
    "detail": {
        "id": 603,
        "title": "The Matrix",
        "release_date": "1999-03-30",
        "genres": [{"name": "Action"}, {"name": "Science Fiction"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Lana Wachowski"}]
        },
    },
}

INCEPTION_2010 = {
    "search": {
        "results": [
            {
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-15",
                "genre_ids": [28, 878],
            }
        ]
    },
    "detail": {
        "id": 27205,
        "title": "Inception",
        "release_date": "2010-07-15",
        "genres": [{"name": "Action"}, {"name": "Science Fiction"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Christopher Nolan"}]
        },
    },
}

THE_GODFATHER_1972 = {
    "search": {
        "results": [
            {
                "id": 238,
                "title": "The Godfather",
                "release_date": "1972-03-14",
                "genre_ids": [18, 80],
            }
        ]
    },
    "detail": {
        "id": 238,
        "title": "The Godfather",
        "release_date": "1972-03-14",
        "genres": [{"name": "Drama"}, {"name": "Crime"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Francis Ford Coppola"}]
        },
    },
}

BLADE_RUNNER_1982 = {
    "search": {
        "results": [
            {
                "id": 78,
                "title": "Blade Runner",
                "release_date": "1982-06-25",
                "genre_ids": [878, 18],
            }
        ]
    },
    "detail": {
        "id": 78,
        "title": "Blade Runner",
        "release_date": "1982-06-25",
        "genres": [{"name": "Science Fiction"}, {"name": "Drama"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Ridley Scott"}]
        },
    },
}

AMELIE_2001 = {
    "search": {
        "results": [
            {
                "id": 194,
                "title": "Amelie",
                "release_date": "2001-04-25",
                "genre_ids": [35, 10749],
            }
        ]
    },
    "detail": {
        "id": 194,
        "title": "Amelie",
        "release_date": "2001-04-25",
        "genres": [{"name": "Comedy"}, {"name": "Romance"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Jean-Pierre Jeunet"}]
        },
    },
}

# Movie with special characters in title (for sanitization tests)
MOVIE_WITH_SPECIAL_CHARS = {
    "search": {
        "results": [
            {
                "id": 99999,
                "title": 'Movie: The "Sequel"',
                "release_date": "2021-01-01",
                "genre_ids": [28],
            }
        ]
    },
    "detail": {
        "id": 99999,
        "title": 'Movie: The "Sequel"',
        "release_date": "2021-01-01",
        "genres": [{"name": "Action"}],
        "credits": {"crew": []},
    },
}

# ---- TV fixtures -----------------------------------------------------------

BREAKING_BAD = {
    "search": {
        "results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 1396,
        "name": "Breaking Bad",
        "first_air_date": "2008-01-20",
        "genres": [{"name": "Drama"}],
        "created_by": [{"name": "Vince Gilligan"}],
        "credits": {"crew": []},
    },
}

THE_WIRE = {
    "search": {
        "results": [
            {
                "id": 1438,
                "name": "The Wire",
                "first_air_date": "2002-06-02",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 1438,
        "name": "The Wire",
        "first_air_date": "2002-06-02",
        "genres": [{"name": "Drama"}],
        "created_by": [{"name": "David Simon"}],
        "credits": {"crew": []},
    },
}

THE_DAILY_SHOW = {
    "search": {
        "results": [
            {
                "id": 2224,
                "name": "The Daily Show",
                "first_air_date": "1996-07-22",
                "genre_ids": [35, 10763],
            }
        ]
    },
    "detail": {
        "id": 2224,
        "name": "The Daily Show",
        "first_air_date": "1996-07-22",
        "genres": [{"name": "Comedy"}, {"name": "News"}],
        "created_by": [],
        "credits": {"crew": []},
    },
}

# Ambiguous: two shows with same name, similar confidence
THE_OFFICE_AMBIGUOUS = {
    "search": {
        "results": [
            {
                "id": 2316,
                "name": "The Office",
                "first_air_date": "2005-03-24",
                "genre_ids": [35],
            },
            {
                "id": 2996,
                "name": "The Office",
                "first_air_date": "2001-07-09",
                "genre_ids": [35],
            },
        ]
    },
    "details": {
        2316: {
            "id": 2316,
            "name": "The Office",
            "first_air_date": "2005-03-24",
            "genres": [{"name": "Comedy"}],
            "created_by": [{"name": "Greg Daniels"}],
            "credits": {"crew": []},
        },
        2996: {
            "id": 2996,
            "name": "The Office",
            "first_air_date": "2001-07-09",
            "genres": [{"name": "Comedy"}],
            "created_by": [{"name": "Ricky Gervais"}],
            "credits": {"crew": []},
        },
    },
}

GENERIC_SHOW = {
    "search": {
        "results": [
            {
                "id": 50000,
                "name": "Show Name",
                "first_air_date": "2020-01-01",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 50000,
        "name": "Show Name",
        "first_air_date": "2020-01-01",
        "genres": [{"name": "Drama"}],
        "created_by": [],
        "credits": {"crew": []},
    },
}

# ---- Empty / error fixtures -----------------------------------------------

EMPTY_SEARCH = {"results": []}


# ---- Mock registration helpers --------------------------------------------


def mock_tmdb(fixture, media_type="movie"):
    """Register responses mocks for a TMDB search + detail lookup.

    Call this inside a ``@responses.activate`` decorated test. Can be called
    multiple times to register multiple titles.

    Args:
        fixture: One of the fixture dicts above (e.g. ``DUNE_2021``).
        media_type: ``"movie"`` or ``"tv"``.
    """
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET,
        f"{BASE_URL}/{endpoint}",
        json=fixture["search"],
    )
    detail_type = "tv" if media_type == "tv" else "movie"
    for result in fixture["search"]["results"]:
        tmdb_id = result["id"]
        detail = fixture.get("detail") or fixture["details"][tmdb_id]
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}/{detail_type}/{tmdb_id}",
            json=detail,
        )


def mock_tmdb_ambiguous(fixture, media_type="tv"):
    """Register mocks for a fixture with multiple results and per-ID details.

    Use for fixtures like ``THE_OFFICE_AMBIGUOUS`` where ``details`` is a dict
    keyed by TMDB ID.
    """
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET,
        f"{BASE_URL}/{endpoint}",
        json=fixture["search"],
    )
    detail_type = "tv" if media_type == "tv" else "movie"
    for result in fixture["search"]["results"]:
        tmdb_id = result["id"]
        detail = fixture["details"][tmdb_id]
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}/{detail_type}/{tmdb_id}",
            json=detail,
        )


def mock_tmdb_by_id(fixture, media_type="movie"):
    """Register a mock for ``get_by_id`` only (no search endpoint).

    Used for NFO-based identification where only the detail endpoint is called.
    """
    detail_type = "tv" if media_type == "tv" else "movie"
    tmdb_id = fixture["detail"]["id"]
    resp_lib.add(
        resp_lib.GET,
        f"{BASE_URL}/{detail_type}/{tmdb_id}",
        json=fixture["detail"],
    )


def mock_tmdb_empty(media_type="movie"):
    """Register a mock that returns no search results."""
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET,
        f"{BASE_URL}/{endpoint}",
        json=EMPTY_SEARCH,
    )


def mock_tmdb_error(status=401, media_type="movie"):
    """Register a mock that returns an HTTP error."""
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET,
        f"{BASE_URL}/{endpoint}",
        status=status,
    )
```

**Verify:**

```bash
uv run python -c "from tests.test_e2e.tmdb_fixtures import mock_tmdb, DUNE_2021; print('OK')"
```

**Commit:** `test: add TMDB response fixtures for E2E tests`

---

## Task 3: Movie import tests (`test_movie_import.py`)

**Depends on:** Tasks 1, 2

**Files:**
- Create: `tests/test_e2e/test_movie_import.py`

**Scenarios:** A1-A12 from the design doc.

**Important implementation details:**

- Use `@responses.activate` on every test function.
- Call `mock_tmdb()` before `service.import_path()`.
- For "unmatched" scenarios (A8, A9, A12), mock with `mock_tmdb_empty()`.
  TMDBSource.search returns `[]` when the query is empty, so no HTTP call is
  made. If a title IS extracted but returns no results, mock the endpoint.
  **Important:** `TMDBSource.search()` returns `[]` immediately when `title`
  is empty string, without hitting HTTP at all. So for truly empty titles, no
  mock is needed -- but use `mock_tmdb_empty()` to be safe in case guessit
  extracts something unexpected.
- For A2 (no year), note that `year_factor` for missing query year is `0.8`.
  The JW similarity for exact title match is ~1.0, so confidence = ~0.8 < 0.9.
  The file will be skipped (not imported) in non-interactive mode.
- For A4 (typo), "Teh Matrx" vs "The Matrix": JW similarity is lower. Even
  with exact year match (factor 1.0), confidence will be below 0.9. Mock TMDB
  to return "The Matrix" (1999).
- For A6 (edition), use a template that includes edition:
  `movie_template="{title} ({year}){edition: - $}/{title} ({year}){edition: - $}{ext}"`
- For A10 (unicode), `Amelie` vs `Amelie` -- note the TMDB fixture title is
  "Amelie" (no accent). The filename has the accent. JW similarity between
  "amelie" and "amelie" (after lowercasing) should be high. The accent in
  "Amelie" is not a Windows-illegal char, so it passes sanitization.
- For A11 (long filename), construct a 200+ char filename like:
  `"A.Really.Long.Movie.Title.That.Goes.On.And.On.2021.1080p.BluRay.x264.DTS-HD.MA.5.1-GROUP.mkv"`
  -- just make it long enough. guessit should still extract the title.

**Template for each test function:**

```python
@responses.activate
def test_a1_clean_scene_release(source_dir, make_service, library):
    # 1. Create source file
    video = make_video(source_dir, "Movie.Name.2021.1080p.BluRay.x264-GROUP.mkv")

    # 2. Mock TMDB (guessit extracts "Movie Name", searches for it)
    # Create a fixture inline or use a pre-built one if title matches
    mock_tmdb(SOME_FIXTURE, media_type="movie")

    # 3. Import
    service, repo = make_service()
    summary = service.import_path(source_dir)

    # 4. Assert summary
    assert summary["imported"] == 1
    assert summary["errors"] == 0

    # 5. Assert destination file exists
    assert_imported(library["movies"], "Movie Name (2021)/Movie Name (2021).mkv",
                    source=video, mode="copy")

    # 6. Assert DB record
    assert_db_record(repo, count=1, title="Movie Name", year=2021,
                     media_type="movie", match_source="filename")
```

For scenarios where guessit extracts a title that doesn't match any pre-built
fixture, create an inline fixture dict or use `responses.add()` directly. The
key requirement is that the TMDB search endpoint receives the query and returns
the expected results so the scoring math works out.

**Full test list:**

| Test function | Scenario | Key assertion |
|---|---|---|
| `test_a1_clean_scene_release` | A1 | auto-accept, correct dest and DB |
| `test_a2_no_year_below_threshold` | A2 | skipped=1, not imported |
| `test_a3_wrong_year_off_by_one` | A3 | auto-accept, DB year from TMDB |
| `test_a4_typo_in_title` | A4 | skipped (low JW similarity) |
| `test_a5_article_normalization` | A5 | auto-accept (article removed) |
| `test_a6_edition_tag` | A6 | edition in dest path |
| `test_a7_mixed_separators` | A7 | title correctly extracted |
| `test_a8_minimal_filename` | A8 | unmatched, no crash |
| `test_a9_obfuscated_hash_name` | A9 | unmatched, no crash |
| `test_a10_unicode_accents` | A10 | imported, filesystem-safe |
| `test_a11_very_long_filename` | A11 | no crash |
| `test_a12_resolution_only` | A12 | unmatched, no crash |

**Verify:**

```bash
uv run pytest tests/test_e2e/test_movie_import.py -v
```

Expected: all 12 tests pass.

**Commit:** `test: add E2E movie import tests (A1-A12)`

---

## Task 4: TV import tests (`test_tv_import.py`)

**Depends on:** Tasks 1, 2

**Files:**
- Create: `tests/test_e2e/test_tv_import.py`

**Scenarios:** B1-B7 from the design doc.

**Important implementation details:**

- TV episodes use `media_type="tv"` for TMDB mocks.
- guessit puts the show name in `result["title"]` when type is "episode", then
  `parse_filename()` moves it to `result["show"]`. The pipeline then searches
  TMDB using `file_info.get("title") or file_info.get("show")`.
- The default TV template is:
  `{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}{episode_title: - $}{ext}`
- For B2 (folder hint), create a nested structure:
  ```
  source_dir/Breaking Bad (2008)/Season 01/S01E01.mkv
  ```
  Pass `source_dir` (not the nested path) to `import_path`. The scanner finds
  the file. `parse_filename("S01E01.mkv", folder_name="Season 01")` won't get
  a show name from "Season 01", but the pipeline uses `folder_name=path.parent.name`.
  Actually -- check this: `parse_filename` gets `folder_name=path.parent.name`
  which is "Season 01". That won't help. The folder hint only helps if guessit
  can extract the title from the folder name. So for B2, use
  `source_dir/Breaking Bad/S01E01.mkv` (show name IS the parent folder).
  Actually, looking at the code in `pipeline.py:67`:
  ```python
  parsed = parse_filename(path.name, folder_name=path.parent.name)
  ```
  So `folder_name` is the immediate parent directory name. If that's
  "Season 01", guessit won't extract a title from it. For the B2 test, put the
  episode directly under the show name folder:
  `source_dir/Breaking Bad (2008)/S01E01.mkv` so `folder_name="Breaking Bad (2008)"`.

- For B3 (multi-episode), no TMDB mock is needed because the pipeline returns
  early before TMDB search. But `mock_tmdb_empty()` is safe to add as a
  fallback. The file will have `requires_interaction=True` and be skipped.
  Note: `is_available()` is still called before the search step in the pipeline.
  Actually no -- looking at the pipeline code, `is_available()` is called at
  step 6, but the multi-episode guard is at step 4. The pipeline returns before
  reaching step 6. So `is_available()` is NOT called. But we pre-set
  `meta._available = True` in the fixture, so it doesn't matter.

- For B4 (daily show), guessit may parse `The.Daily.Show.2024.01.15.mkv` as
  having a date field rather than season/episode. The pipeline checks
  `"season" in file_info` to determine media type. If guessit doesn't extract
  season/episode, the pipeline will search TMDB as a movie (since no season
  field). This test should verify the pipeline doesn't crash regardless of how
  guessit parses it. The assertion should be flexible: either it identifies as
  TV and imports, or it's unmatched/skipped. No crash is the key invariant.

- For B5 (ambiguous), use `THE_OFFICE_AMBIGUOUS` fixture. Both results will
  have similar JW scores. The pipeline should set `requires_interaction=True`
  because the top candidate's confidence is below threshold (no year in filename
  = 0.8 factor, and both results are "The Office" = 1.0 JW).

- For B7 (season pack), create 3 files in the same directory and mock TMDB
  to return the same show for each search query. TMDB mocks with `responses`
  use `responses.add()` which by default allows multiple calls to the same URL.
  But each search hit also triggers a detail fetch. Register the search mock
  once and the detail mock once -- `responses` replays them.
  **Important:** `responses.add()` creates a one-shot mock by default unless
  you use `responses.add(..., match_querystring=False)` or register multiple
  times. Actually, `responses` v0.20+ replays by default. Check: the existing
  tests use `resp_lib.add()` and it works for single calls. For 3 files each
  triggering a search + detail, register the search mock 3 times and the detail
  mock 3 times. Or better: use `responses.add()` with `match_querystring=False`
  -- no, `responses.add()` with the same URL adds multiple responses that are
  consumed in order. Simplest approach: call `mock_tmdb(fixture, "tv")` 3 times.

**Full test list:**

| Test function | Scenario | Key assertion |
|---|---|---|
| `test_b1_standard_tv_episode` | B1 | correct TV path, DB fields |
| `test_b2_folder_name_fallback` | B2 | show name from folder |
| `test_b3_multi_episode_skipped` | B3 | skipped, multi_episode flag |
| `test_b4_daily_show` | B4 | no crash, graceful handling |
| `test_b5_ambiguous_show_name` | B5 | requires_interaction |
| `test_b6_anime_style_naming` | B6 | no crash |
| `test_b7_season_pack` | B7 | 3 episodes, correct metadata |

**Verify:**

```bash
uv run pytest tests/test_e2e/test_tv_import.py -v
```

Expected: all 7 tests pass.

**Commit:** `test: add E2E TV import tests (B1-B7)`

---

## Task 5: Directory structure tests (`test_directory_structures.py`)

**Depends on:** Tasks 1, 2

**Files:**
- Create: `tests/test_e2e/test_directory_structures.py`

**Scenarios:** C1-C7 from the design doc.

**Important implementation details:**

- For C1 (flat mixed), create 4 files: 2 valid videos, 1 txt (ignored by
  scanner -- not a video extension), 1 sample (excluded by `_SAMPLE_PATTERN`).
  The sample pattern matches stems like `sample`, `sample-foo`, `foo-sample`,
  `foo sample bar`. Create a file named `sample.mkv` -- its stem is `sample`
  which matches `^sample$`.

- For C2 (scene release folder), create a subdirectory with the scene release
  name. Put the video, NFO, and SRT inside. Create a `Sample/` subdirectory
  with `sample-movie.mkv` inside (excluded by scanner). The NFO here is NOT
  used for identification (it's a plain text NFO without TMDB ID structure, or
  we simply don't put a `<tmdbid>` tag in it). For a clean test, make the NFO
  a companion file (not an identification NFO). Write it as plain text or as
  XML without a TMDB ID tag. The SRT should be moved as a companion. The NFO
  should be moved as a companion (category NFO, moved by default).

  **Wait:** The NFO scanner (`scan_for_nfo_id`) will try to parse ALL `*.nfo`
  files in the directory and up to 2 parents. If the NFO has valid XML with a
  `<tmdbid>` tag, it will be used for identification. If it has invalid XML or
  no TMDB ID, `_parse_nfo` returns None and identification falls through to
  guessit + TMDB search.

  For C2, we want the normal guessit + TMDB flow (not NFO identification). So
  make the NFO contain valid XML but no TMDB ID:
  ```xml
  <movie><title>Movie Name</title></movie>
  ```
  This will parse but `scan_for_nfo_id` returns None (no tmdbid tag).

- For C3 (nested TV), create 3 episodes across 2 seasons. Each episode
  triggers its own TMDB search. Mock TMDB to return the same show. Register
  mocks 3 times (once per search call).

- For C4 (RAR artifacts), the `.r00`, `.r01`, `.nzb` files have extensions not
  in `VIDEO_EXTENSIONS`, so the scanner ignores them. The subtitle in `Subs/`
  subdirectory is found by the companion classifier (which does `rglob("*")` in
  the video's parent directory). **But wait:** the video is in
  `Movie.Name.2021/` and the subtitle is in `Movie.Name.2021/Subs/`. The
  companion classifier scans `video_path.parent.rglob("*")` which is
  `Movie.Name.2021/` -- it will find `Subs/Movie.Name.2021.en.srt`. Good.

- For C5 (single file), pass the file path directly to `import_path()` instead
  of a directory. `scan_media_files` handles single files:
  ```python
  if root.is_file():
      if root.suffix.lower() in VIDEO_EXTENSIONS and not _SAMPLE_PATTERN.search(root.stem):
          return [root]
  ```

- For C6 and C7, no TMDB mocks are needed (no video files found).

**Full test list:**

| Test function | Scenario | Key assertion |
|---|---|---|
| `test_c1_flat_mixed_directory` | C1 | 2 imported, txt ignored, sample excluded |
| `test_c2_scene_release_folder` | C2 | video + companions, sample excluded |
| `test_c3_nested_tv_structure` | C3 | 3 episodes, correct paths |
| `test_c4_rar_extract_artifacts` | C4 | only video imported, artifacts ignored |
| `test_c5_single_file_import` | C5 | single file works |
| `test_c6_empty_directory` | C6 | imported=0, no errors |
| `test_c7_non_video_files_only` | C7 | imported=0, no errors |

**Verify:**

```bash
uv run pytest tests/test_e2e/test_directory_structures.py -v
```

Expected: all 7 tests pass.

**Commit:** `test: add E2E directory structure tests (C1-C7)`

---

## Task 6: Companion file tests (`test_companions.py`)

**Depends on:** Tasks 1, 2

**Files:**
- Create: `tests/test_e2e/test_companions.py`

**Scenarios:** D1-D8 from the design doc.

**Important implementation details:**

- Companions are classified by `classify_companions(video_path)` which scans
  the video's parent directory recursively. It uses `fnmatch` patterns
  (case-insensitive) defined in `DEFAULT_PATTERNS`.

- `rename_companion(original_name, dest_stem, category)`:
  - SUBTITLE with 3+ dot-segments: preserves last 2 segments as lang+ext
    (e.g., `movie.en.srt` -> `Dune (2021).en.srt`)
  - NFO: replaces everything with `dest_stem.nfo`
  - Everything else: keeps original name

- Companions are moved using the same mode as the video (copy/move/link/hardlink).

- `move_by_default` by category:
  - SUBTITLE: True
  - ARTWORK: True
  - NFO: True
  - SAMPLE: False
  - UNKNOWN: False

- For D4 (artwork), artwork filenames like `poster.jpg` and `fanart.jpg` match
  the ARTWORK patterns. They are moved by default. `rename_companion` for
  ARTWORK returns the original name (not renamed to match video).

- For D5 (sample not moved), the file `sample-Movie.mkv` has extension `.mkv`
  which is in `VIDEO_EXTENSIONS` in the companion classifier -- so it's skipped
  by the classifier (line 79: `if f.suffix.lower() in VIDEO_EXTENSIONS: continue`).
  Also, the discovery scanner excludes it via `_SAMPLE_PATTERN`. So the sample
  never reaches the companion system at all.

- For D6 (companion in subdir), `classify_companions` uses `rglob("*")` and
  stores `relative_to_video = f.relative_to(parent)`. During move,
  `_move_companions` uses `dest_video.parent / comp.relative_to_video.parent / new_name`.
  So if `relative_to_video` is `Subs/movie.en.srt`, the companion goes to
  `<dest_dir>/Subs/Dune (2021).en.srt`.

- For D7 and D8, verify source file state after import. In move mode, both
  video and companion sources should be deleted. In link mode, both should be
  symlinked and sources preserved.

**Full test list:**

| Test function | Scenario | Key assertion |
|---|---|---|
| `test_d1_subtitle_with_lang_tag` | D1 | renamed with lang tag preserved |
| `test_d2_multiple_subtitle_languages` | D2 | all 3 subtitles renamed |
| `test_d3_nfo_companion` | D3 | NFO renamed to match video |
| `test_d4_artwork_files` | D4 | poster.jpg, fanart.jpg moved |
| `test_d5_sample_file_excluded` | D5 | sample not in library |
| `test_d6_companion_in_subdirectory` | D6 | relative path preserved |
| `test_d7_companion_move_mode` | D7 | sources deleted |
| `test_d8_companion_link_mode` | D8 | symlinks, sources preserved |

**Verify:**

```bash
uv run pytest tests/test_e2e/test_companions.py -v
```

Expected: all 8 tests pass.

**Commit:** `test: add E2E companion file tests (D1-D8)`

---

## Task 7: Edge case tests (`test_edge_cases.py`)

**Depends on:** Tasks 1, 2

**Files:**
- Create: `tests/test_e2e/test_edge_cases.py`

**Scenarios:** E1-E16 from the design doc.

**Important implementation details:**

- For E1 (re-import), import a file, then call `import_path` again on the same
  source directory. The DB cache lookup matches on path + mtime + size. Since
  the file hasn't changed, the second import skips it.
  **But wait:** in copy mode, the source file still exists at the original path.
  The DB record stores the DESTINATION path, not the source path. So the cache
  lookup uses `str(path)` where `path` is the source file. The DB has the dest
  path. These don't match. The file won't be a cache hit based on path.

  Let me re-read the pipeline:
  ```python
  cached = self._repo.find_by_path_stat(str(path), stat.st_mtime, stat.st_size)
  ```
  And `_write_db_record` stores `path=str(dst)`. So the DB has the dest path,
  but the pipeline queries with the source path. These are different. The cache
  will miss.

  For E1 to work, we need to import the DESTINATION directory (the library),
  not the source. Or import in move mode so the file is now at the dest path,
  then re-import the library directory.

  Actually, re-reading the E1 scenario: "Import Movie.mkv -> success, DB record
  written. Import same directory again." In copy mode, the source file still
  exists and will be re-identified and re-imported (to the same dest, which
  already exists). This may cause an overwrite or error.

  The correct interpretation: use move mode so the file is at the dest path
  after first import. Then import the library directory -- the file is found,
  DB cache matches (path=dest, mtime/size match), and it's skipped.

  Or: use copy mode and import the source directory again. The file will be
  re-identified and the pipeline will try to copy it again to the same dest.
  Since the dest already exists, `copy_verify` will overwrite it (or error).

  Let's make E1 use move mode. After first import, the file is at the dest.
  Import the dest directory (library) -- cache hit, skipped.

- For E2 (modified re-import), use move mode. After first import, modify the
  dest file (append bytes to change mtime and size). Then import the library
  directory again. Cache misses because mtime/size changed. Re-identified.

- For E3 (dry-run), verify `summary["planned"]` has correct entries AND that no
  files exist in the library AND no DB records exist.

- For E9 (TMDB network error), use `responses.add()` with
  `body=ConnectionError()`. But first -- `is_available()` is called before
  `search()`. We pre-set `_available = True`. Then `search()` calls
  `requests.get()` which hits the mock. If we register a ConnectionError for
  the search endpoint, it will raise, and `TMDBSource.search` catches it:
  ```python
  except Exception as e:
      logger.warning("TMDB search failed: %s", e)
      return []
  ```
  So it returns empty results. The file is unmatched.

  Actually, we need to be more careful. The `responses` library intercepts ALL
  HTTP calls when `@responses.activate` is used. If we DON'T register a mock
  for an endpoint that gets called, `responses` raises `ConnectionError` by
  default. So for E9, we can simply not register any TMDB mocks and it will
  raise ConnectionError.

  But wait -- we pre-set `_available = True`. So `is_available()` doesn't make
  an HTTP call. Good. Then `search()` calls `requests.get(search_url)` which
  hits the `responses` interceptor with no matching mock -> ConnectionError.
  `search()` catches it and returns `[]`. Good.

- For E10 (HTTP error), register the search endpoint with `status=401`.

- For E11 (NFO identification), create an NFO with `<tmdbid>438631</tmdbid>`.
  The pipeline finds it, calls `metadata_source.get_by_id(438631, "movie")`.
  Mock the TMDB detail endpoint for movie 438631. The NFO path returns
  confidence=0.95 and source="nfo".

- For E13 (illegal chars), mock TMDB to return `'Movie: The "Sequel"'` as
  the title. The template engine applies the replace table first:
  `": "` -> `" - "`. Then sanitizes Windows-illegal chars (`"` removed).
  Expected dest title: `Movie - The Sequel`.

- For E14 (threshold boundary), we need precise confidence control. The scoring
  is `jaro_winkler(normalized_query, normalized_result) * year_factor`. For an
  exact title match with exact year, confidence = 1.0 * 1.0 = 1.0. We can't
  easily get exactly 0.90. Instead: use threshold=0.80 and test with a file
  that scores ~0.80 (e.g., missing year: JW=1.0 * 0.8 = 0.80). With
  threshold=0.80, confidence=0.80 should auto-accept (>= 0.80). With
  threshold=0.81, it should require interaction.

- For E15 (partial failure), mock the file operation to raise an error for one
  file. Use `unittest.mock.patch` on `ImportService._execute_file_op` with a
  `side_effect` that raises for a specific file. Actually, for a true E2E test,
  we could make the dest directory read-only for one file. But that's fragile.
  Simpler: patch `copy_verify` to raise `IOError` for a specific source path.

- For E16 (DB field correctness), this is a thorough check of all fields in
  the DB record after import.

**Full test list:**

| Test function | Scenario | Key assertion |
|---|---|---|
| `test_e1_reimport_cache_hit` | E1 | skipped on second import |
| `test_e2_modified_file_reimport` | E2 | re-identified after modification |
| `test_e3_dry_run_no_side_effects` | E3 | planned entries, no files/DB |
| `test_e4_move_mode` | E4 | source deleted |
| `test_e5_copy_mode` | E5 | source preserved |
| `test_e6_link_mode` | E6 | symlink created |
| `test_e7_hardlink_mode` | E7 | same inode |
| `test_e8_no_db_mode` | E8 | no DB/session records |
| `test_e9_tmdb_network_error` | E9 | unmatched, no crash |
| `test_e10_tmdb_http_error` | E10 | unmatched, no crash |
| `test_e11_nfo_identification` | E11 | match_source="nfo", conf=0.95 |
| `test_e12_tvshow_nfo` | E12 | media_type="tv" from NFO |
| `test_e13_illegal_chars_in_title` | E13 | sanitized dest path |
| `test_e14_threshold_boundary` | E14 | exact boundary behavior |
| `test_e15_partial_failure` | E15 | 1 imported, 1 error |
| `test_e16_db_field_correctness` | E16 | all fields verified |

**Verify:**

```bash
uv run pytest tests/test_e2e/test_edge_cases.py -v
```

Expected: all 16 tests pass.

**Commit:** `test: add E2E edge case tests (E1-E16)`

---

## Final verification

After all tasks complete, run the full E2E suite and the full project test suite:

```bash
uv run pytest tests/test_e2e/ -v          # all 50 E2E tests
uv run pytest                              # full suite (319 existing + 50 new)
```

Expected: all tests pass, no regressions.
