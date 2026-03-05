import os
import sqlite3

import pytest

from tapes.config.schema import (
    ImportConfig,
    LibraryConfig,
    TapesConfig,
    TemplatesConfig,
)
from tapes.db.repository import Repository
from tapes.db.schema import init_db
from tapes.importer.service import ImportService
from tapes.metadata.tmdb import TMDBSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Factory: build a TapesConfig with sensible E2E defaults."""

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
                movie=movie_template
                or "{title} ({year})/{title} ({year}){ext}",
                tv=tv_template
                or "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d}{episode_title: - $}{ext}",
            ),
        )

    return _make


@pytest.fixture
def make_service(repo, make_config):
    """Factory: build an ImportService wired to the in-memory repo.

    Returns (service, repo).
    """

    def _make(**config_overrides):
        cfg = make_config(**config_overrides)
        meta = TMDBSource(token="fake-token")
        meta._available = True  # skip /configuration HTTP check
        service = ImportService(repo=repo, metadata_source=meta, config=cfg)
        return service, repo

    return _make


# ---------------------------------------------------------------------------
# Helper functions (module-level, importable by test files)
# ---------------------------------------------------------------------------


def make_video(directory, name, size=1024):
    """Create a dummy video file with random bytes."""
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(size))
    return path


def make_nfo(directory, name, tmdb_id, root_tag="movie"):
    """Create an NFO file containing a TMDB ID."""
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<{root_tag}><tmdbid>{tmdb_id}</tmdbid></{root_tag}>"
    )
    return path


def assert_imported(library_dir, rel_path, *, source=None, mode="copy"):
    """Assert a file was imported to the expected library path."""
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

    Use field__gte for >= checks (e.g., confidence__gte=0.9).
    """
    items = repo.get_all_items()
    if count is not None:
        assert len(items) == count, (
            f"Expected {count} DB records, got {len(items)}"
        )
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
            if (
                getattr(item, field, None) is None
                or getattr(item, field) < minimum
            ):
                match = False
                break
        if match:
            return item

    field_desc = ", ".join(f"{k}={v}" for k, v in field_checks.items())
    item_desc = "\n  ".join(str(vars(i)) for i in items)
    raise AssertionError(
        f"No DB record matching {field_desc}.\nRecords:\n  {item_desc}"
    )
