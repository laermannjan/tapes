"""Tests for tapes.grouper -- dict-based group merging."""

from pathlib import Path

from tapes.grouper import group_files, same_multi_part, same_season
from tapes.models import (
    FileEntry,
    FileMetadata,
    GroupType,
    ImportGroup,
)


def _group(
    title: str | None = None,
    media_type: str | None = None,
    year: int | None = None,
    season: int | None = None,
    episode: int | None = None,
    part: int | None = None,
    files: list[Path] | None = None,
) -> ImportGroup:
    """Helper to build an ImportGroup with video files."""
    meta = FileMetadata(
        media_type=media_type,
        title=title,
        year=year,
        season=season,
        episode=episode,
        part=part,
    )
    g = ImportGroup(metadata=meta)
    for p in files or []:
        g.add_file(FileEntry(path=p))
    return g


class TestSameSeason:
    def test_merge_same_show_same_season(self):
        g1 = _group("Breaking Bad", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g2 = _group("Breaking Bad", "episode", season=1, episode=2, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        assert len(result) == 1
        assert len(result[0].files) == 2

    def test_no_merge_different_season(self):
        g1 = _group("Breaking Bad", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g2 = _group("Breaking Bad", "episode", season=2, episode=1, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        assert len(result) == 2

    def test_no_merge_different_show(self):
        g1 = _group("Breaking Bad", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g2 = _group("Better Call Saul", "episode", season=1, episode=1, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        assert len(result) == 2

    def test_case_insensitive_title(self):
        g1 = _group("Breaking Bad", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g2 = _group("breaking bad", "episode", season=1, episode=2, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        assert len(result) == 1

    def test_skips_movies(self):
        g1 = _group("Inception", "movie", year=2010, files=[Path("inc.mkv")])
        g2 = _group("Inception", "movie", year=2010, files=[Path("inc2.mkv")])
        result = same_season([g1, g2])
        assert len(result) == 2

    def test_skips_episodes_without_season(self):
        g1 = _group("Show", "episode", episode=1, files=[Path("ep1.mkv")])
        g2 = _group("Show", "episode", episode=2, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        assert len(result) == 2

    def test_single_episode_stays_standalone(self):
        g1 = _group("Show", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        result = same_season([g1])
        assert len(result) == 1
        assert result[0].group_type == GroupType.STANDALONE

    def test_assigns_season_type(self):
        g1 = _group("Show", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g2 = _group("Show", "episode", season=1, episode=2, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        assert result[0].group_type == GroupType.SEASON


class TestSameMultiPart:
    def test_merge_same_title_with_parts(self):
        g1 = _group("Kill Bill", "movie", part=1, files=[Path("kb1.mkv")])
        g2 = _group("Kill Bill", "movie", part=2, files=[Path("kb2.mkv")])
        result = same_multi_part([g1, g2])
        assert len(result) == 1
        assert len(result[0].files) == 2

    def test_no_merge_without_parts(self):
        g1 = _group("Inception", "movie", files=[Path("inc.mkv")])
        g2 = _group("Inception", "movie", files=[Path("inc2.mkv")])
        result = same_multi_part([g1, g2])
        assert len(result) == 2

    def test_no_merge_only_one_has_part(self):
        g1 = _group("Kill Bill", "movie", part=1, files=[Path("kb1.mkv")])
        g2 = _group("Kill Bill", "movie", files=[Path("kb2.mkv")])
        result = same_multi_part([g1, g2])
        assert len(result) == 2

    def test_assigns_multi_part_type(self):
        g1 = _group("Kill Bill", "movie", part=1, files=[Path("kb1.mkv")])
        g2 = _group("Kill Bill", "movie", part=2, files=[Path("kb2.mkv")])
        result = same_multi_part([g1, g2])
        assert result[0].group_type == GroupType.MULTI_PART


class TestGroupFiles:
    def test_full_pipeline_mixed_content(self):
        groups = [
            _group("Show", "episode", season=1, episode=1, files=[Path("s01e01.mkv")]),
            _group("Show", "episode", season=1, episode=2, files=[Path("s01e02.mkv")]),
            _group("Show", "episode", season=2, episode=1, files=[Path("s02e01.mkv")]),
            _group("Kill Bill", "movie", part=1, files=[Path("kb1.mkv")]),
            _group("Kill Bill", "movie", part=2, files=[Path("kb2.mkv")]),
            _group("Inception", "movie", year=2010, files=[Path("inc.mkv")]),
        ]
        result = group_files(groups)
        # Season 1 merged, season 2 standalone, Kill Bill merged, Inception standalone
        assert len(result) == 4
        season_groups = [g for g in result if g.group_type == GroupType.SEASON]
        assert len(season_groups) == 1
        assert len(season_groups[0].files) == 2
        multi_part = [g for g in result if g.group_type == GroupType.MULTI_PART]
        assert len(multi_part) == 1
        assert len(multi_part[0].files) == 2
        standalone = [g for g in result if g.group_type == GroupType.STANDALONE]
        assert len(standalone) == 2

    def test_preserves_companions_through_merge(self):
        g1 = _group("Show", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g1.add_file(FileEntry(path=Path("ep1.srt"), role="subtitle"))
        g2 = _group("Show", "episode", season=1, episode=2, files=[Path("ep2.mkv")])
        g2.add_file(FileEntry(path=Path("ep2.nfo"), role="metadata"))
        result = same_season([g1, g2])
        assert len(result) == 1
        merged = result[0]
        paths = {f.path for f in merged.files}
        assert Path("ep1.mkv") in paths
        assert Path("ep1.srt") in paths
        assert Path("ep2.mkv") in paths
        assert Path("ep2.nfo") in paths

    def test_files_point_to_merged_group(self):
        g1 = _group("Show", "episode", season=1, episode=1, files=[Path("ep1.mkv")])
        g2 = _group("Show", "episode", season=1, episode=2, files=[Path("ep2.mkv")])
        result = same_season([g1, g2])
        merged = result[0]
        for f in merged.files:
            assert f.group is merged
