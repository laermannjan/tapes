"""Tests for mock TMDB query."""
from tapes.ui.query import mock_tmdb_lookup


def test_confident_match():
    result = mock_tmdb_lookup("Dune")
    assert result is not None
    fields, confidence = result
    assert fields["title"] == "Dune"
    assert confidence >= 0.9


def test_uncertain_match():
    result = mock_tmdb_lookup("Breaking Bad")
    assert result is not None
    fields, confidence = result
    assert fields["title"] == "Breaking Bad"
    assert confidence < 0.9


def test_no_match():
    result = mock_tmdb_lookup("nonexistent")
    assert result is None


def test_empty_title():
    result = mock_tmdb_lookup("")
    assert result is None


def test_episode_specific_data():
    result = mock_tmdb_lookup("Breaking Bad", episode=1)
    assert result is not None
    fields, _ = result
    assert fields["episode_title"] == "Pilot"


def test_episode_specific_data_ep2():
    result = mock_tmdb_lookup("Breaking Bad", episode=2)
    assert result is not None
    fields, _ = result
    assert fields["episode_title"] == "Cat's in the Bag..."
