"""Tests for conflict resolution and language config fields."""

from tapes.config import MetadataConfig, TapesConfig


class TestConflictConfig:
    def test_defaults(self) -> None:
        cfg = TapesConfig()
        assert cfg.metadata.duplicate_resolution == "auto"
        assert cfg.metadata.disambiguation == "auto"
        assert cfg.metadata.language == ""

    def test_override(self) -> None:
        cfg = TapesConfig(metadata=MetadataConfig(duplicate_resolution="warn", disambiguation="off", language="de"))
        assert cfg.metadata.duplicate_resolution == "warn"
        assert cfg.metadata.disambiguation == "off"
        assert cfg.metadata.language == "de"
