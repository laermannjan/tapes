import pytest
from tapes.config.schema import TapesConfig, MetadataConfig, LibraryConfig
from tapes.validation import validate_config, ConfigError


def _cfg(tmdb_token="", movies="", tv=""):
    return TapesConfig(
        metadata=MetadataConfig(tmdb_token=tmdb_token),
        library=LibraryConfig(movies=movies, tv=tv),
    )


def test_valid_config_passes(monkeypatch):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    cfg = _cfg(tmdb_token="mytoken", movies="~/Movies")
    validate_config(cfg)  # must not raise


def test_missing_tmdb_token_raises(monkeypatch):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    cfg = _cfg(tmdb_token="", movies="~/Movies")
    with pytest.raises(ConfigError, match="TMDB read access token"):
        validate_config(cfg)


def test_tmdb_token_from_env(monkeypatch):
    monkeypatch.setenv("TMDB_TOKEN", "envtoken")
    cfg = _cfg(tmdb_token="", movies="~/Movies")
    validate_config(cfg)  # env var should satisfy the check


def test_missing_library_paths_raises(monkeypatch):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    cfg = _cfg(tmdb_token="mytoken", movies="", tv="")
    with pytest.raises(ConfigError, match="No library paths"):
        validate_config(cfg)


def test_tv_only_library_passes(monkeypatch):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    cfg = _cfg(tmdb_token="mytoken", movies="", tv="~/TV")
    validate_config(cfg)  # tv-only is fine
