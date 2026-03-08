"""Tests for tapes.pipeline module."""

from __future__ import annotations

import pytest

from tapes.pipeline import _TmdbCache


class TestTmdbCache:
    def test_cache_retries_after_failure(self) -> None:
        """Failed cache fetches should allow retry on next request."""
        cache = _TmdbCache()
        call_count = 0

        def failing_then_succeeding():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return "result"

        with pytest.raises(RuntimeError):
            cache.get_or_fetch(("key",), failing_then_succeeding)

        result = cache.get_or_fetch(("key",), failing_then_succeeding)
        assert result == "result"
        assert call_count == 2

    def test_cache_returns_cached_result(self) -> None:
        """Successful fetch should be cached and returned on subsequent requests."""
        cache = _TmdbCache()
        call_count = 0

        def fetcher():
            nonlocal call_count
            call_count += 1
            return "cached_value"

        result1 = cache.get_or_fetch(("key",), fetcher)
        result2 = cache.get_or_fetch(("key",), fetcher)
        assert result1 == "cached_value"
        assert result2 == "cached_value"
        assert call_count == 1  # fetcher only called once
