"""End-to-end tests for the full scan -> extract -> companions -> group pipeline."""

from __future__ import annotations

from tapes.models import GroupType
from tapes.pipeline import run_pipeline


# ---------------------------------------------------------------------------
# Movie scenarios
# ---------------------------------------------------------------------------


class TestMovieScenarios:
    """Movies: standalone, with companions, multi-part, multiple unrelated."""

    def test_single_movie_with_two_subtitles(self, tmp_path, make_video, make_companion):
        """Single movie with 2 subtitle companions -> 1 group, 3 files."""
        make_video("Inception.2010.1080p.BluRay.mkv")
        make_companion("Inception.2010.1080p.BluRay.srt")
        make_companion("Inception.2010.1080p.BluRay.en.srt")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        assert g.group_type == GroupType.STANDALONE
        assert len(g.files) == 3
        assert len(g.video_files) == 1
        subtitles = [f for f in g.files if f.role == "subtitle"]
        assert len(subtitles) == 2

    def test_movie_in_release_folder_with_subtitle(
        self, tmp_path, make_video, make_companion
    ):
        """Movie in release folder with subtitle companion -> 1 group, 2 files."""
        make_video(
            "The.Matrix.1999.1080p.mkv",
            subdir="The.Matrix.1999.1080p.BluRay",
        )
        make_companion(
            "The.Matrix.1999.1080p.srt",
            subdir="The.Matrix.1999.1080p.BluRay",
        )

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        assert len(g.files) == 2
        assert g.metadata.title is not None
        assert "matrix" in g.metadata.title.lower()

    def test_multi_part_movie(self, tmp_path, make_video):
        """Multi-part movie (CD1/CD2) -> 1 group, MULTI_PART type."""
        make_video("Kill.Bill.2003.CD1.mkv")
        make_video("Kill.Bill.2003.CD2.mkv")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        assert g.group_type == GroupType.MULTI_PART
        assert len(g.video_files) == 2

    def test_two_unrelated_movies(self, tmp_path, make_video):
        """Two unrelated movies -> 2 separate groups."""
        make_video("Inception.2010.mkv")
        make_video("The.Matrix.1999.mkv")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 2
        titles = {g.metadata.title.lower() for g in groups if g.metadata.title}
        assert "inception" in titles
        assert "the matrix" in titles


# ---------------------------------------------------------------------------
# TV scenarios
# ---------------------------------------------------------------------------


class TestTVScenarios:
    """TV shows: season grouping, per-episode subtitles, multi-season, standalone."""

    def test_season_folder_three_episodes(self, tmp_path, make_video):
        """Season folder with 3 episodes -> 3 groups, each STANDALONE."""
        for ep in range(1, 4):
            make_video(
                f"Breaking.Bad.S01E{ep:02d}.mkv",
                subdir="Breaking.Bad.S01",
            )

        groups = run_pipeline(tmp_path)

        assert len(groups) == 3
        for g in groups:
            assert g.group_type == GroupType.STANDALONE
            assert len(g.video_files) == 1

    def test_episodes_with_per_episode_subtitles(
        self, tmp_path, make_video, make_companion
    ):
        """Episodes with per-episode subtitles -> 2 groups, each STANDALONE with 1 video + 1 subtitle."""
        for ep in range(1, 3):
            stem = f"The.Office.S02E{ep:02d}"
            make_video(f"{stem}.mkv", subdir="The.Office.S02")
            make_companion(f"{stem}.srt", subdir="The.Office.S02")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 2
        for g in groups:
            assert g.group_type == GroupType.STANDALONE
            assert len(g.video_files) == 1
            subtitles = [f for f in g.files if f.role == "subtitle"]
            assert len(subtitles) == 1

    def test_multiple_seasons_stay_separate(self, tmp_path, make_video):
        """Episodes from different seasons -> 4 separate groups, all STANDALONE."""
        make_video("Show.S01E01.mkv", subdir="Show.S01")
        make_video("Show.S01E02.mkv", subdir="Show.S01")
        make_video("Show.S02E01.mkv", subdir="Show.S02")
        make_video("Show.S02E02.mkv", subdir="Show.S02")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 4
        for g in groups:
            assert g.group_type == GroupType.STANDALONE

    def test_single_episode_stays_standalone(self, tmp_path, make_video):
        """A single episode with no peers -> STANDALONE type."""
        make_video("Friends.S03E07.mkv")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        assert g.group_type == GroupType.STANDALONE
        assert g.metadata.media_type == "episode"


# ---------------------------------------------------------------------------
# Mixed scenarios
# ---------------------------------------------------------------------------


class TestMixedScenarios:
    """Movies and episodes together, sample exclusion."""

    def test_movies_and_episodes_together(self, tmp_path, make_video):
        """A movie and two episodes -> 3 groups, all STANDALONE."""
        make_video("Inception.2010.mkv")
        make_video("Show.S01E01.mkv", subdir="Show.S01")
        make_video("Show.S01E02.mkv", subdir="Show.S01")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 3
        for g in groups:
            assert g.group_type == GroupType.STANDALONE

    def test_sample_files_excluded(self, tmp_path, make_video):
        """Sample files should not appear in any group."""
        make_video("Movie.2020.mkv")
        make_video("Movie.2020.sample.mkv")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        all_paths = [f.path.name for g in groups for f in g.files]
        assert "Movie.2020.sample.mkv" not in all_paths


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Empty dirs, numeric filenames, hidden dirs, deep nesting, back-refs."""

    def test_empty_directory(self, tmp_path):
        """Empty directory -> empty list."""
        groups = run_pipeline(tmp_path)
        assert groups == []

    def test_no_metadata_fallback_numeric_filename(self, tmp_path, make_video):
        """Numeric filename -> still produces a group with a label."""
        make_video("12345.mkv")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        assert g.label  # should have some label, not empty

    def test_hidden_directory_excluded(self, tmp_path, make_video):
        """Files inside hidden directories should be excluded."""
        make_video("Movie.2020.mkv", subdir=".hidden")

        groups = run_pipeline(tmp_path)

        assert groups == []

    def test_deeply_nested_file_found(self, tmp_path, make_video):
        """A video file several levels deep should still be discovered."""
        make_video(
            "Deep.Movie.2021.mkv",
            subdir="level1/level2/level3",
        )

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        assert groups[0].metadata.title is not None

    def test_bidirectional_refs_intact(self, tmp_path, make_video, make_companion):
        """Every FileEntry.group points back to its owning ImportGroup."""
        make_video("Ref.Test.2022.mkv")
        make_companion("Ref.Test.2022.srt")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        for entry in g.files:
            assert entry.group is g, (
                f"FileEntry {entry.path.name} has wrong group back-reference"
            )
