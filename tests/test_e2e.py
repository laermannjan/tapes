"""End-to-end tests for critical user flows.

Each test creates real files on disk, mocks TMDB, runs the full app
pipeline, and asserts real outcomes (files at destinations, tree state).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapes.config import LibraryConfig, ModeConfig, TapesConfig

# ---------------------------------------------------------------------------
# TMDB mock responses
# ---------------------------------------------------------------------------

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"


def _mock_search_multi(query: str, token: str, year: int | None = None, **kwargs: object) -> list[dict]:
    q = query.lower()
    if "dune" in q:
        return [
            {"tmdb_id": 438631, "title": "Dune", "year": 2021, "media_type": "movie"},
            {"tmdb_id": 841, "title": "Dune", "year": 1984, "media_type": "movie"},
        ]
    if "the matrix" in q:
        return [{"tmdb_id": 603, "title": "The Matrix", "year": 1999, "media_type": "movie"}]
    if "breaking bad" in q:
        return [{"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"}]
    if "inception" in q:
        return [{"tmdb_id": 27205, "title": "Inception", "year": 2010, "media_type": "movie"}]
    return []


def _mock_get_show(tmdb_id: int, token: str, **kwargs: object) -> dict:
    if tmdb_id == 1396:
        return {
            "tmdb_id": 1396,
            "title": "Breaking Bad",
            "year": 2008,
            "media_type": "episode",
            "seasons": [1, 2, 3, 4, 5],
        }
    return {}


def _mock_get_season_episodes(
    show_id: int, season_number: int, token: str, show_title: str = "", show_year: int | None = None, **kwargs: object
) -> list[dict]:
    if show_id == 1396 and season_number == 1:
        return [
            {
                "tmdb_id": 1396,
                "title": "Breaking Bad",
                "year": 2008,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
                "episode_title": "Pilot",
            },
            {
                "tmdb_id": 1396,
                "title": "Breaking Bad",
                "year": 2008,
                "media_type": "episode",
                "season": 1,
                "episode": 2,
                "episode_title": "Cat's in the Bag...",
            },
        ]
    return []


@pytest.fixture
def mock_tmdb():
    with (
        patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi),
        patch("tapes.tmdb.get_show", side_effect=_mock_get_show),
        patch("tapes.tmdb.get_season_episodes", side_effect=_mock_get_season_episodes),
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    tmp_path: Path,
    *,
    auto_commit: bool = False,
    headless: bool = False,
    poll_interval: float = 0.0,
    conflict_resolution: str = "auto",
    delete_rejected: bool = False,
    operation: str = "copy",
) -> TapesConfig:
    movies_dir = tmp_path / "library" / "movies"
    tv_dir = tmp_path / "library" / "tv"
    movies_dir.mkdir(parents=True, exist_ok=True)
    tv_dir.mkdir(parents=True, exist_ok=True)
    return TapesConfig(
        metadata={"tmdb_token": "fake-token"},  # ty: ignore[invalid-argument-type]  # Pydantic dict coercion
        library=LibraryConfig(
            movies=str(movies_dir),
            tv=str(tv_dir),
            movie_template=MOVIE_TEMPLATE,
            tv_template=TV_TEMPLATE,
            operation=operation,  # ty: ignore[invalid-argument-type]
            conflict_resolution=conflict_resolution,  # ty: ignore[invalid-argument-type]
            delete_rejected=delete_rejected,
        ),
        mode=ModeConfig(
            auto_commit=auto_commit,
            auto_commit_delay=0.1,
            headless=headless,
            poll_interval=poll_interval,
        ),
        dry_run=False,
    )


def _build_app(tmp_path: Path, source_dir: Path, config: TapesConfig):
    from tapes.scanner import scan
    from tapes.tree_model import build_tree
    from tapes.ui.tree_app import TreeApp

    files = scan(source_dir)
    model = build_tree(files, source_dir)
    app = TreeApp(
        model=model,
        movie_template=config.library.movie_template,
        tv_template=config.library.tv_template,
        root_path=source_dir,
        auto_pipeline=True,
        config=config,
    )
    return app, model


def _create_movie(source_dir: Path, name: str, size: int = 1024) -> Path:
    p = source_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00" * size)
    return p


# ---------------------------------------------------------------------------
# E2E: One-shot movie processing
# ---------------------------------------------------------------------------


try:
    from textual.pilot import Pilot  # noqa: F401

    HAS_PILOT = True
except ImportError:
    HAS_PILOT = False


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestOneShot:
    """One-shot headless: scan, identify, auto-commit, exit."""

    @pytest.mark.asyncio()
    async def test_movie_identified_and_committed(self, tmp_path: Path, mock_tmdb: None) -> None:
        """A movie file is scanned, identified via TMDB, auto-committed to library."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "The.Matrix.1999.1080p.mkv")

        cfg = _make_config(tmp_path, auto_commit=True, headless=True)
        app, _model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            # Wait for pipeline + auto-commit
            await pilot.pause(1.0)

        # Movie should be copied to library
        dest = Path(cfg.library.movies) / "The Matrix (1999)" / "The Matrix (1999).mkv"
        assert dest.exists(), f"Expected {dest} to exist"

    @pytest.mark.asyncio()
    async def test_tv_episode_identified_and_committed(self, tmp_path: Path, mock_tmdb: None) -> None:
        """A TV episode is scanned, identified via TMDB, auto-committed to library."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "Breaking.Bad.S01E01.Pilot.720p.mkv")

        cfg = _make_config(tmp_path, auto_commit=True, headless=True)
        app, _model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(1.0)

        dest = Path(cfg.library.tv) / "Breaking Bad (2008)" / "Season 01" / "Breaking Bad - S01E01 - Pilot.mkv"
        assert dest.exists(), f"Expected {dest} to exist"

    @pytest.mark.asyncio()
    async def test_unidentified_file_stays_pending(self, tmp_path: Path, mock_tmdb: None) -> None:
        """A file that TMDB can't identify stays PENDING, not processed."""
        source_dir = tmp_path / "source"
        src = _create_movie(source_dir, "random_video.mkv")

        cfg = _make_config(tmp_path, auto_commit=True, headless=True)
        app, model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(1.0)

        # Source file should still exist (not processed)
        assert src.exists()
        # Should still be in tree as PENDING
        files = model.all_files()
        assert len(files) == 1
        assert files[0].pending


# ---------------------------------------------------------------------------
# E2E: Conflict resolution
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestConflictE2E:
    """Conflict resolution during auto-commit."""

    @pytest.mark.asyncio()
    async def test_auto_largest_wins(self, tmp_path: Path, mock_tmdb: None) -> None:
        """With auto policy, largest file wins when two target same destination."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "Inception.2010.720p.mkv", size=1000)
        _create_movie(source_dir, "Inception.2010.2160p.mkv", size=5000)

        cfg = _make_config(tmp_path, auto_commit=True, headless=True, conflict_resolution="auto")
        app, _model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(1.0)

        dest = Path(cfg.library.movies) / "Inception (2010)" / "Inception (2010).mkv"
        assert dest.exists()
        # Larger file should have won
        assert dest.stat().st_size == 5000

    @pytest.mark.asyncio()
    async def test_keep_all_creates_suffixed_copies(self, tmp_path: Path, mock_tmdb: None) -> None:
        """With keep_all policy, all files get processed with numeric suffixes."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "Inception.2010.720p.mkv", size=1000)
        _create_movie(source_dir, "Inception.2010.1080p.mkv", size=3000)

        cfg = _make_config(tmp_path, auto_commit=True, headless=True, conflict_resolution="keep_all")
        app, _model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(1.0)

        dest_dir = Path(cfg.library.movies) / "Inception (2010)"
        files = list(dest_dir.iterdir()) if dest_dir.exists() else []
        assert len(files) == 2, f"Expected 2 files, got {files}"

    @pytest.mark.asyncio()
    async def test_delete_rejected_removes_loser(self, tmp_path: Path, mock_tmdb: None) -> None:
        """With delete_rejected, the conflict loser's source file is deleted."""
        source_dir = tmp_path / "source"
        small = _create_movie(source_dir, "Inception.2010.720p.mkv", size=1000)
        _create_movie(source_dir, "Inception.2010.2160p.mkv", size=5000)

        cfg = _make_config(tmp_path, auto_commit=True, headless=True, delete_rejected=True)
        app, _model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(3.0)

        # Both files should have been committed/rejected via conflict resolution
        dest = Path(cfg.library.movies) / "Inception (2010)" / "Inception (2010).mkv"
        assert dest.exists(), f"Expected {dest} to exist (winner should be processed)"
        assert dest.stat().st_size == 5000, "Larger file should win"
        # Small file should be deleted (rejected + delete_rejected)
        assert not small.exists(), "Rejected file should be deleted"


# ---------------------------------------------------------------------------
# E2E: TUI manual staging flow
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestTUIFlow:
    """Interactive TUI flows via pilot keypresses."""

    @pytest.mark.asyncio()
    async def test_stage_and_commit(self, tmp_path: Path, mock_tmdb: None) -> None:
        """User stages a file with space, opens commit with Tab, confirms with Enter."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "The.Matrix.1999.1080p.mkv")

        cfg = _make_config(tmp_path)  # No auto-commit
        app, model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            # Wait for TMDB pipeline to finish and callbacks to process
            await pilot.pause(2.0)

            # File should already be auto-staged by the pipeline
            files = model.all_files()
            staged = [f for f in files if f.staged]

            if not staged:
                # Pipeline didn't auto-stage - try manual staging
                # Navigate to file and stage it
                await pilot.press("j")
                await pilot.pause(0.1)
                await pilot.press("space")
                await pilot.pause(0.1)
                files = model.all_files()
                staged = [f for f in files if f.staged]

            assert len(staged) >= 1, "Expected at least one staged file"

            # Open commit view
            await pilot.press("tab")
            await pilot.pause(0.1)

            # Confirm commit
            await pilot.press("enter")
            await pilot.pause(0.5)

        # File should be in library
        dest = Path(cfg.library.movies) / "The Matrix (1999)" / "The Matrix (1999).mkv"
        assert dest.exists(), f"Expected {dest} to exist"

    @pytest.mark.asyncio()
    async def test_reject_file(self, tmp_path: Path, mock_tmdb: None) -> None:
        """User rejects a file with x, it becomes REJECTED."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "The.Matrix.1999.1080p.mkv")

        cfg = _make_config(tmp_path)
        app, model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Navigate to the file
            await pilot.press("j")
            await pilot.pause(0.1)

            # Reject the file
            await pilot.press("x")

            files = model.all_files()
            assert len(files) == 1
            assert files[0].rejected


# ---------------------------------------------------------------------------
# E2E: Polling
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestPollingE2E:
    """Directory polling picks up new files."""

    @pytest.mark.asyncio()
    async def test_new_file_detected_during_polling(self, tmp_path: Path, mock_tmdb: None) -> None:
        """A file added after initial scan is picked up by polling."""
        source_dir = tmp_path / "source"
        _create_movie(source_dir, "The.Matrix.1999.1080p.mkv")

        cfg = _make_config(tmp_path, poll_interval=0.5)
        app, model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            initial_count = len(model.all_files())

            # Add a new file
            _create_movie(source_dir, "Dune.2021.2160p.mkv")

            # Wait for poll to detect it
            await pilot.pause(1.0)

            new_count = len(model.all_files())
            assert new_count > initial_count, f"Expected more files after poll, got {initial_count} -> {new_count}"

    @pytest.mark.asyncio()
    async def test_removed_file_detected_during_polling(self, tmp_path: Path, mock_tmdb: None) -> None:
        """A file deleted from disk is removed from the tree by polling."""
        source_dir = tmp_path / "source"
        to_remove = _create_movie(source_dir, "The.Matrix.1999.1080p.mkv")
        _create_movie(source_dir, "Dune.2021.2160p.mkv")

        cfg = _make_config(tmp_path, poll_interval=0.5)
        app, model = _build_app(tmp_path, source_dir, cfg)

        async with app.run_test() as pilot:
            await pilot.pause(0.5)
            assert len(model.all_files()) == 2

            # Remove a file from disk
            to_remove.unlink()

            # Wait for poll
            await pilot.pause(1.0)

            assert len(model.all_files()) == 1
