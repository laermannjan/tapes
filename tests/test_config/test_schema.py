import pytest
from tapes.config.schema import TapesConfig


def test_defaults():
    cfg = TapesConfig()
    assert cfg.import_.mode == "copy"
    assert cfg.import_.confidence_threshold == 0.9
    assert cfg.companions.move.subtitle is True
    assert cfg.companions.move.unknown is False


def test_invalid_mode():
    with pytest.raises(Exception):
        TapesConfig(import_={"mode": "invalid"})


def test_library_defaults():
    cfg = TapesConfig()
    assert cfg.library.movies == ""
    assert cfg.library.tv == ""


def test_replace_defaults():
    cfg = TapesConfig()
    assert ": " in cfg.replace
    assert cfg.replace[": "] == " - "
