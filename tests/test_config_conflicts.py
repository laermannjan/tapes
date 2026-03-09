"""Tests for conflict resolution, language, and verify config fields."""

from tapes.config import LibraryConfig, MetadataConfig, TapesConfig


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


class TestVerifyConfig:
    def test_verify_defaults_true(self) -> None:
        cfg = TapesConfig()
        assert cfg.library.verify is True

    def test_verify_override_false(self) -> None:
        cfg = TapesConfig(library=LibraryConfig(verify=False))
        assert cfg.library.verify is False
