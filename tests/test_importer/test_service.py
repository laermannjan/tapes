import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.config.schema import TapesConfig, LibraryConfig, ImportConfig, TemplatesConfig
from tapes.metadata.base import SearchResult
from tapes.identification.pipeline import IdentificationResult
from tapes.importer.service import ImportService


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return Repository(conn)


@pytest.fixture
def cfg(tmp_path):
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    return TapesConfig(
        library=LibraryConfig(movies=str(movies_dir), tv=""),
        import_=ImportConfig(dry_run=False, mode="copy", confidence_threshold=0.8),
        templates=TemplatesConfig(movie="{title} ({year}){ext}"),
    )


@pytest.fixture
def meta_source():
    return MagicMock()


def _make_candidate(title="The Matrix", year=1999, confidence=0.90):
    return SearchResult(
        tmdb_id=603,
        title=title,
        year=year,
        media_type="movie",
        confidence=confidence,
    )


def _make_video(tmp_path, name="movie.mkv"):
    f = tmp_path / name
    f.write_bytes(b"\x00" * 1024)
    return f


def test_dry_run_no_files(tmp_path, repo, meta_source, cfg):
    cfg.import_.dry_run = True
    empty = tmp_path / "empty"
    empty.mkdir()

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    summary = service.import_path(empty)

    assert summary["imported"] == 0
    assert summary["planned"] == []


def test_dry_run_planned(tmp_path, repo, meta_source, cfg):
    cfg.import_.dry_run = True
    video = _make_video(tmp_path)
    candidate = _make_candidate()

    mock_result = IdentificationResult(candidates=[candidate], file_info={})
    with patch.object(
        ImportService, "_process_file",
        side_effect=lambda v, summary, session: (
            summary.planned.append({"source": str(v), "title": candidate.title})
            or setattr(summary, "imported", summary.imported + 1)
        )
    ):
        service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
        # Directly test dry-run path via pipeline mock
        pass

    # Use real pipeline mock instead
    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        with patch.object(service, "_execute_file_op"):
            with patch.object(service, "_write_db_record"):
                summary = service.import_path(tmp_path)

    assert summary["dry_run"] is True
    assert summary["imported"] == 1
    assert len(summary["planned"]) == 1
    assert summary["planned"][0]["title"] == "The Matrix"


def test_already_in_db_skipped(tmp_path, repo, meta_source, cfg):
    video = _make_video(tmp_path)
    from tapes.db.repository import ItemRecord
    from datetime import datetime, timezone
    stat = video.stat()
    item = ItemRecord(
        id=None, path=str(video), media_type="movie", tmdb_id=603,
        title="The Matrix", year=1999, show=None, season=None, episode=None,
        episode_title=None, director=None, genre=None, edition=None,
        codec=None, resolution=None, audio=None, hdr=0, match_source="tmdb",
        confidence=0.90, mtime=stat.st_mtime, size=stat.st_size,
        imported_at=datetime.now(timezone.utc).isoformat(),
    )
    repo.upsert_item(item)

    mock_result = IdentificationResult(item=item, candidates=[], file_info={})
    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        summary = service.import_path(tmp_path)

    assert summary["skipped"] == 1
    assert summary["imported"] == 0


def test_unmatched_no_candidates(tmp_path, repo, meta_source, cfg):
    video = _make_video(tmp_path)
    mock_result = IdentificationResult(candidates=[], file_info={})

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        summary = service.import_path(tmp_path)

    assert str(video) in summary["unmatched"]
    assert summary["skipped"] == 1


def test_execute_copy(tmp_path, repo, meta_source, cfg):
    cfg.import_.mode = "copy"
    video = _make_video(tmp_path)
    candidate = _make_candidate()
    mock_result = IdentificationResult(candidates=[candidate], file_info={})

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    assert summary["errors"] == 0
    # destination file should exist
    dest = Path(cfg.library.movies) / "The Matrix (1999).mkv"
    assert dest.exists()
