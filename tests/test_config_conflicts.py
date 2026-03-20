"""Tests for conflict resolution and language config fields."""

from tapes.config import LibraryConfig, TapesConfig


class TestConflictConfig:
    def test_defaults(self) -> None:
        cfg = TapesConfig()
        assert cfg.library.conflict_resolution == "auto"
        assert cfg.library.delete_rejected is False
        assert cfg.metadata.language == ""

    def test_override(self) -> None:
        cfg = TapesConfig(library=LibraryConfig(conflict_resolution="skip", delete_rejected=True))
        assert cfg.library.conflict_resolution == "skip"
        assert cfg.library.delete_rejected is True
