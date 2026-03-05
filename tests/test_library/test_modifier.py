import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from tapes.db.schema import init_db
from tapes.db.repository import Repository, ItemRecord
from tapes.config.schema import TapesConfig, LibraryConfig, TemplatesConfig
from tapes.metadata.base import SearchResult
from tapes.library.modifier import modify_item, ModifyResult


@pytest.fixture
def setup(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repo = Repository(conn)

    movies_root = tmp_path / "movies"
    movies_root.mkdir()

    cfg = TapesConfig(
        library=LibraryConfig(movies=str(movies_root)),
        templates=TemplatesConfig(movie="{title} ({year})/{title} ({year}){ext}"),
    )
    return repo, conn, cfg, movies_root


def _insert_item(conn, path, title="Film", year=2020, media_type="movie", tmdb_id=None):
    conn.execute(
        """INSERT INTO items (path, media_type, tmdb_id, title, year, mtime, size, imported_at)
           VALUES (?, ?, ?, ?, ?, 0, 0, datetime('now'))""",
        (str(path), media_type, tmdb_id, title, year),
    )
    conn.commit()


def _make_tmdb_source(result: SearchResult | None = None):
    source = MagicMock()
    source.get_by_id.return_value = result
    return source


class TestModifyItemNotFound:
    def test_item_not_in_db(self, setup):
        repo, conn, cfg, root = setup
        tmdb = _make_tmdb_source()
        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=root / "nonexistent.mkv", tmdb_id="tmdb:12345",
        )
        assert not result.ok
        assert "not found" in result.error.lower()

    def test_path_resolved_for_lookup(self, setup, tmp_path):
        repo, conn, cfg, root = setup
        # File exists but not in DB
        f = root / "somefile.mkv"
        f.touch()
        tmdb = _make_tmdb_source()
        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=f, tmdb_id="tmdb:12345",
        )
        assert not result.ok
        assert "not found" in result.error.lower()


class TestModifyWithTmdbId:
    def test_updates_metadata_from_tmdb(self, setup):
        repo, conn, cfg, root = setup
        old = root / "wrong.mkv"
        old.write_bytes(b"video")
        _insert_item(conn, old, "Wrong Title", 2019, tmdb_id=99999)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
            director="Denis Villeneuve", genre="Science Fiction",
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=old, tmdb_id="tmdb:438631",
        )

        assert result.ok
        tmdb.get_by_id.assert_called_once_with(438631, "movie")

        # DB should be updated
        items = repo.get_all_items()
        assert len(items) == 1
        assert items[0].title == "Dune"
        assert items[0].year == 2021
        assert items[0].tmdb_id == 438631
        assert items[0].director == "Denis Villeneuve"

    def test_renames_file_on_disk(self, setup):
        repo, conn, cfg, root = setup
        old = root / "wrong.mkv"
        old.write_bytes(b"video data")
        _insert_item(conn, old, "Wrong Title", 2019)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=old, tmdb_id="tmdb:438631",
        )

        assert result.ok
        assert not old.exists()
        new_path = root / "Dune (2021)" / "Dune (2021).mkv"
        assert new_path.exists()
        assert new_path.read_bytes() == b"video data"

        # DB path should be updated too
        items = repo.get_all_items()
        assert items[0].path == str(new_path)

    def test_no_move_flag_skips_rename(self, setup):
        repo, conn, cfg, root = setup
        old = root / "wrong.mkv"
        old.write_bytes(b"video")
        _insert_item(conn, old, "Wrong Title", 2019)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=old, tmdb_id="tmdb:438631", no_move=True,
        )

        assert result.ok
        # File stays in place
        assert old.exists()
        # DB metadata updated but path unchanged
        items = repo.get_all_items()
        assert items[0].title == "Dune"
        assert items[0].path == str(old)

    def test_no_rename_when_path_unchanged(self, setup):
        repo, conn, cfg, root = setup
        correct = root / "Dune (2021)" / "Dune (2021).mkv"
        correct.parent.mkdir(parents=True)
        correct.write_bytes(b"video")
        _insert_item(conn, correct, "Dune", 2021, tmdb_id=438631)

        # Re-identify with same metadata
        same_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.99,
        )
        tmdb = _make_tmdb_source(same_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=correct, tmdb_id="tmdb:438631",
        )

        assert result.ok
        assert correct.exists()
        assert not result.moved  # no rename needed

    def test_tmdb_lookup_fails(self, setup):
        repo, conn, cfg, root = setup
        f = root / "movie.mkv"
        f.write_bytes(b"video")
        _insert_item(conn, f, "Title", 2020)

        tmdb = _make_tmdb_source(None)  # returns None

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=f, tmdb_id="tmdb:999999",
        )

        assert not result.ok
        assert "not found" in result.error.lower() or "tmdb" in result.error.lower()


class TestModifyTvShow:
    def test_modifies_tv_item(self, setup, tmp_path):
        repo, conn, cfg, root = setup
        tv_root = tmp_path / "tv"
        tv_root.mkdir()
        cfg.library.tv = str(tv_root)
        cfg.templates.tv = "{show}/Season {season:02d}/{show} S{season:02d}E{episode:02d}{ext}"

        old = tv_root / "wrong.mkv"
        old.write_bytes(b"video")
        _insert_item(conn, old, "Wrong", 2019, media_type="tv")

        new_meta = SearchResult(
            tmdb_id=1399, title="Breaking Bad", year=2008,
            media_type="tv", confidence=0.95,
            show="Breaking Bad", season=1, episode=1,
            episode_title="Pilot",
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=old, tmdb_id="tmdb:1399",
        )

        assert result.ok
        new_path = tv_root / "Breaking Bad" / "Season 01" / "Breaking Bad S01E01.mkv"
        assert new_path.exists()
        items = repo.get_all_items()
        assert items[0].show == "Breaking Bad"
        assert items[0].path == str(new_path)


class TestModifyDirectory:
    def test_modifies_all_items_under_directory(self, setup):
        repo, conn, cfg, root = setup
        show_dir = root / "Wrong Show"
        show_dir.mkdir()
        ep1 = show_dir / "ep1.mkv"
        ep2 = show_dir / "ep2.mkv"
        ep1.write_bytes(b"video1")
        ep2.write_bytes(b"video2")
        _insert_item(conn, ep1, "Ep1", 2020)
        _insert_item(conn, ep2, "Ep2", 2020)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=show_dir, tmdb_id="tmdb:438631",
        )

        assert result.ok
        assert result.items_modified == 2


class TestModifyEventEmission:
    def test_emits_after_write_event(self, setup):
        repo, conn, cfg, root = setup
        f = root / "movie.mkv"
        f.write_bytes(b"video")
        _insert_item(conn, f, "Title", 2020)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
        )
        tmdb = _make_tmdb_source(new_meta)
        bus = MagicMock()

        modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=f, tmdb_id="tmdb:438631", event_bus=bus,
        )

        bus.emit.assert_called_once()
        call_kwargs = bus.emit.call_args
        assert call_kwargs[0][0] == "after_write"
        assert call_kwargs[1]["title"] == "Dune"
        assert call_kwargs[1]["tmdb_id"] == 438631

    def test_no_event_when_no_bus(self, setup):
        """No crash when event_bus is None."""
        repo, conn, cfg, root = setup
        f = root / "movie.mkv"
        f.write_bytes(b"video")
        _insert_item(conn, f, "Title", 2020)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=f, tmdb_id="tmdb:438631", event_bus=None,
        )
        assert result.ok


class TestModifyCompanions:
    def test_moves_subtitle_alongside_video(self, setup):
        repo, conn, cfg, root = setup
        old = root / "wrong.mkv"
        old.write_bytes(b"video")
        sub = root / "wrong.en.srt"
        sub.write_text("subtitle content")
        _insert_item(conn, old, "Wrong", 2019)

        new_meta = SearchResult(
            tmdb_id=438631, title="Dune", year=2021,
            media_type="movie", confidence=0.95,
        )
        tmdb = _make_tmdb_source(new_meta)

        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=old, tmdb_id="tmdb:438631",
        )

        assert result.ok
        assert result.moved
        new_sub = root / "Dune (2021)" / "Dune (2021).en.srt"
        assert new_sub.exists()
        assert new_sub.read_text() == "subtitle content"


class TestModifyIdParsing:
    def test_invalid_id_format(self, setup):
        repo, conn, cfg, root = setup
        f = root / "movie.mkv"
        f.write_bytes(b"video")
        _insert_item(conn, f, "Title", 2020)

        tmdb = _make_tmdb_source()
        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=f, tmdb_id="invalid",
        )
        assert not result.ok
        assert "id" in result.error.lower()

    def test_id_without_prefix(self, setup):
        repo, conn, cfg, root = setup
        f = root / "movie.mkv"
        f.write_bytes(b"video")
        _insert_item(conn, f, "Title", 2020)

        tmdb = _make_tmdb_source()
        result = modify_item(
            repo=repo, config=cfg, metadata_source=tmdb,
            path=f, tmdb_id="438631",
        )
        assert not result.ok
        assert "tmdb:" in result.error.lower()
