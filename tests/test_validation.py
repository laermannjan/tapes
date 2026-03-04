import pytest
from tapes.config.schema import TapesConfig, MetadataConfig, LibraryConfig
from tapes.validation import validate_config, ConfigError


def _cfg(tmdb_key="", movies="", tv=""):
    return TapesConfig(
        metadata=MetadataConfig(tmdb_api_key=tmdb_key),
        library=LibraryConfig(movies=movies, tv=tv),
    )


def test_valid_config_passes(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    cfg = _cfg(tmdb_key="mykey", movies="~/Movies")
    validate_config(cfg)  # must not raise


def test_missing_tmdb_key_raises(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    cfg = _cfg(tmdb_key="", movies="~/Movies")
    with pytest.raises(ConfigError, match="TMDB API key"):
        validate_config(cfg)


def test_tmdb_key_from_env(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "envkey")
    cfg = _cfg(tmdb_key="", movies="~/Movies")
    validate_config(cfg)  # env var should satisfy the check


def test_missing_library_paths_raises(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    cfg = _cfg(tmdb_key="mykey", movies="", tv="")
    with pytest.raises(ConfigError, match="No library paths"):
        validate_config(cfg)


def test_tv_only_library_passes(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    cfg = _cfg(tmdb_key="mykey", movies="", tv="~/TV")
    validate_config(cfg)  # tv-only is fine
