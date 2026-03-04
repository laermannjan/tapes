import pytest
from pathlib import Path
from tapes.config.loader import load_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.import_.mode == "copy"


def test_valid_toml(tmp_path):
    toml = tmp_path / "tapes.toml"
    toml.write_text('[import]\nmode = "move"\n', encoding="utf-8")
    cfg = load_config(toml)
    assert cfg.import_.mode == "move"


def test_import_key_renamed(tmp_path):
    """TOML uses [import] but pydantic field is import_."""
    toml = tmp_path / "tapes.toml"
    toml.write_text('[import]\nconfidence_threshold = 0.75\n', encoding="utf-8")
    cfg = load_config(toml)
    assert cfg.import_.confidence_threshold == 0.75


def test_invalid_toml_exits(tmp_path):
    toml = tmp_path / "tapes.toml"
    toml.write_bytes(b"not valid toml ][[[")
    with pytest.raises(SystemExit):
        load_config(toml)


def test_no_path_uses_defaults():
    """With no config file present in cwd, returns defaults."""
    cfg = load_config(Path("/nonexistent/path/tapes.toml"))
    assert cfg.library.movies == ""
