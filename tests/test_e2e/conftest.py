"""Shared fixtures for E2E pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def make_video(tmp_path: Path):
    """Factory fixture: create a fake video file (1024 bytes).

    Usage::

        video = make_video("Movie.Name.2024.mkv")
        video = make_video("episode.mkv", subdir="Season 01")
    """

    def _make(name: str, subdir: str | None = None) -> Path:
        directory = tmp_path / subdir if subdir else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(b"\x00" * 1024)
        return path

    return _make


@pytest.fixture
def make_companion(tmp_path: Path):
    """Factory fixture: create a companion file.

    Usage::

        sub = make_companion("Movie.Name.2024.srt")
        sub = make_companion("Movie.Name.2024.en.srt", subdir="Subs")
    """

    def _make(name: str, subdir: str | None = None, content: str = "") -> Path:
        directory = tmp_path / subdir if subdir else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(content)
        return path

    return _make
