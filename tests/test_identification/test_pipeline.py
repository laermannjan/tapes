from unittest.mock import MagicMock, patch
from pathlib import Path
from tapes.identification.pipeline import IdentificationPipeline, IdentificationResult
from tapes.metadata.base import SearchResult


def _make_file(tmp_path, name="Dune.2021.mkv", content=b"\x00" * 100):
    f = tmp_path / name
    f.write_bytes(content)
    return f


def _mock_result(confidence=0.95):
    return SearchResult(
        tmdb_id=438631, title="Dune", year=2021,
        media_type="movie", confidence=confidence,
        director="Denis Villeneuve", genre="Science Fiction",
    )


def test_db_cache_hit_returns_immediately(tmp_path):
    repo = MagicMock()
    cached = MagicMock()
    repo.find_by_path_stat.return_value = cached
    f = _make_file(tmp_path)

    pipeline = IdentificationPipeline(repo=repo, metadata_source=MagicMock())
    result = pipeline.identify(f)

    assert result.item == cached
    assert result.source == "db_cache"
    assert not result.requires_interaction
    repo.find_by_path_stat.assert_called_once()


def test_auto_accepts_high_confidence(tmp_path):
    repo = MagicMock()
    repo.find_by_path_stat.return_value = None
    meta = MagicMock()
    meta.is_available.return_value = True
    meta.search.return_value = [_mock_result(confidence=0.95)]
    f = _make_file(tmp_path)

    with patch("tapes.identification.pipeline.scan_for_nfo_id", return_value=None):
        pipeline = IdentificationPipeline(repo=repo, metadata_source=meta, confidence_threshold=0.9)
        result = pipeline.identify(f)

    assert not result.requires_interaction
    assert result.candidates[0].confidence == 0.95
    assert result.source == "filename"


def test_requires_interaction_on_low_confidence(tmp_path):
    repo = MagicMock()
    repo.find_by_path_stat.return_value = None
    meta = MagicMock()
    meta.is_available.return_value = True
    meta.search.return_value = [_mock_result(confidence=0.60)]
    f = _make_file(tmp_path, name="108-wow.mkv")

    with patch("tapes.identification.pipeline.scan_for_nfo_id", return_value=None):
        pipeline = IdentificationPipeline(repo=repo, metadata_source=meta, confidence_threshold=0.9)
        result = pipeline.identify(f)

    assert result.requires_interaction is True


def test_requires_interaction_on_no_results(tmp_path):
    repo = MagicMock()
    repo.find_by_path_stat.return_value = None
    meta = MagicMock()
    meta.is_available.return_value = True
    meta.search.return_value = []
    f = _make_file(tmp_path, name="unknown.mkv")

    with patch("tapes.identification.pipeline.scan_for_nfo_id", return_value=None):
        pipeline = IdentificationPipeline(repo=repo, metadata_source=meta)
        result = pipeline.identify(f)

    assert result.requires_interaction is True
    assert result.candidates == []


def test_nfo_hit_used_directly(tmp_path):
    repo = MagicMock()
    repo.find_by_path_stat.return_value = None
    meta = MagicMock()
    meta.get_by_id.return_value = _mock_result(confidence=0.95)
    f = _make_file(tmp_path)

    with patch("tapes.identification.pipeline.scan_for_nfo_id", return_value=("tmdb", 438631)):
        pipeline = IdentificationPipeline(repo=repo, metadata_source=meta)
        result = pipeline.identify(f)

    assert result.source == "nfo"
    assert result.candidates[0].tmdb_id == 438631
    meta.get_by_id.assert_called_once_with(438631, "movie")


def test_multi_episode_routes_to_interaction(tmp_path):
    repo = MagicMock()
    repo.find_by_path_stat.return_value = None
    meta = MagicMock()
    meta.is_available.return_value = True
    # Even if TMDB returns a confident result, multi-episode must go interactive
    meta.search.return_value = [_mock_result(confidence=0.95)]
    f = _make_file(tmp_path, name="The.Wire.S01E01E02.mkv")

    with patch("tapes.identification.pipeline.scan_for_nfo_id", return_value=None):
        pipeline = IdentificationPipeline(repo=repo, metadata_source=meta, confidence_threshold=0.9)
        result = pipeline.identify(f)

    assert result.requires_interaction is True
    assert result.multi_episode is True
