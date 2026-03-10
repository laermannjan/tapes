"""Tests for tapes.extract -- guessit wrapper and FileMetadata extraction."""

from __future__ import annotations

from tapes.extract import extract_metadata


class TestMovieDetection:
    def test_basic_movie(self):
        m = extract_metadata("The.Matrix.1999.1080p.BluRay.x264.mkv")
        assert m.media_type == "movie"
        assert m.title == "The Matrix"
        assert m.year == 1999

    def test_movie_no_year(self):
        m = extract_metadata("Inception.1080p.BluRay.mkv")
        assert m.media_type == "movie"
        assert m.title == "Inception"
        assert m.year is None


class TestEpisodeDetection:
    def test_basic_episode(self):
        m = extract_metadata("Breaking.Bad.S02E03.1080p.mkv")
        assert m.media_type == "episode"
        assert m.title == "Breaking Bad"
        assert m.season == 2
        assert m.episode == 3

    def test_multi_episode(self):
        m = extract_metadata("Breaking.Bad.S02E03E04.1080p.mkv")
        assert m.media_type == "episode"
        assert m.episode == 3  # normalized to first episode

    def test_single_episode_is_int(self):
        """A single episode should remain an int (not wrapped in a list)."""
        m = extract_metadata("Show.S01E05.mkv")
        assert isinstance(m.episode, int)
        assert m.episode == 5

    def test_episode_no_season(self):
        m = extract_metadata("Show.E05.mkv")
        assert m.media_type == "episode"
        assert m.episode == 5
        assert m.season is None


class TestPartAndCd:
    def test_part(self):
        m = extract_metadata("Movie.2020.Part.3.mkv")
        assert m.part == 3

    def test_cd(self):
        m = extract_metadata("Movie.2020.CD2.mkv")
        assert m.part == 2

    def test_part_preferred_over_cd(self):
        """If both part and cd appear, part wins."""
        m = extract_metadata("Movie.2020.Part.1.CD2.mkv")
        assert m.part is not None


class TestFolderFallback:
    def test_folder_provides_title_and_year(self):
        m = extract_metadata("1080p.mkv", folder_name="The Matrix (1999)")
        assert m.title == "The Matrix"
        assert m.year == 1999

    def test_folder_not_used_when_filename_has_title(self):
        m = extract_metadata(
            "Inception.2010.BluRay.mkv",
            folder_name="Wrong Title (2000)",
        )
        assert m.title == "Inception"
        assert m.year == 2010

    def test_folder_provides_year_only(self):
        """If filename has title but no year, folder can supply year."""
        m = extract_metadata("Inception.BluRay.mkv", folder_name="Stuff (2010)")
        # Filename provides title
        assert m.title == "Inception"
        # Folder provides year
        assert m.year == 2010


class TestRawPreserved:
    def test_raw_contains_normalized_keys(self):
        m = extract_metadata("Movie.2020.1080p.BluRay.x264.DTS.mkv")
        assert "codec" in m.raw
        assert "media_source" in m.raw
        assert "resolution" in m.raw

    def test_old_keys_not_in_raw(self):
        m = extract_metadata("Movie.2020.1080p.BluRay.x264.DTS.mkv")
        assert "video_codec" not in m.raw
        assert "source" not in m.raw
        assert "audio_codec" not in m.raw


class TestFieldNormalization:
    def test_video_codec_renamed(self):
        m = extract_metadata("Movie.2020.1080p.x264.mkv")
        assert "codec" in m.raw
        assert "video_codec" not in m.raw

    def test_source_renamed(self):
        m = extract_metadata("Movie.2020.BluRay.mkv")
        assert "media_source" in m.raw
        assert "source" not in m.raw

    def test_audio_codec_renamed(self):
        m = extract_metadata("Movie.2020.DTS.mkv")
        assert "audio" in m.raw
        assert "audio_codec" not in m.raw


class TestOtherSplitting:
    def test_hdr_extracted(self):
        m = extract_metadata("Movie.2020.HDR.2160p.mkv")
        assert m.raw.get("hdr") == "HDR10"

    def test_dolby_vision_extracted(self):
        m = extract_metadata("Movie.2020.Dolby.Vision.2160p.mkv")
        assert m.raw.get("hdr") == "Dolby Vision"

    def test_hdr_and_dv_combined(self):
        m = extract_metadata("Movie.2020.HDR.DV.2160p.mkv")
        assert "HDR10" in m.raw.get("hdr", "")
        assert "Dolby Vision" in m.raw.get("hdr", "")

    def test_3d_extracted(self):
        m = extract_metadata("Avatar.2009.3D.SBS.1080p.BluRay.mkv")
        assert m.raw.get("three_d") == "3D"

    def test_remux_extracted(self):
        m = extract_metadata("Movie.2020.REMUX.2160p.mkv")
        assert m.raw.get("remux") == "Remux"

    def test_proper_stays_in_other(self):
        m = extract_metadata("Movie.2020.Proper.720p.mkv")
        assert m.raw.get("other") == "Proper"
        assert "hdr" not in m.raw

    def test_mixed_other_split(self):
        m = extract_metadata("Movie.2020.PROPER.REMUX.HDR10.DV.3D.2160p.mkv")
        assert "HDR10" in m.raw.get("hdr", "")
        assert m.raw.get("three_d") == "3D"
        assert m.raw.get("remux") == "Remux"
        assert m.raw.get("other") == "Proper"

    def test_edition_extracted(self):
        m = extract_metadata("The.Matrix.1999.Directors.Cut.1080p.BluRay.mkv")
        assert m.raw.get("edition") == "Director's Cut"

    def test_imax_edition(self):
        m = extract_metadata("Movie.2020.IMAX.2160p.mkv")
        assert m.raw.get("edition") == "IMAX"


class TestPartInRaw:
    def test_part_flows_to_raw(self):
        m = extract_metadata("Movie.2020.Part.2.mkv")
        assert m.part == 2
        assert m.raw.get("part") == 2

    def test_cd_flows_to_raw(self):
        m = extract_metadata("Movie.2020.CD1.mkv")
        assert m.part == 1
        assert m.raw.get("part") == 1


class TestScreenSizeRenamed:
    def test_screen_size_renamed_to_resolution(self):
        m = extract_metadata("Movie.2020.1080p.mkv")
        assert "resolution" in m.raw
        assert "screen_size" not in m.raw


class TestNoTitle:
    def test_no_title_returns_none(self):
        m = extract_metadata("1080p.mkv")
        assert m.title is None

    def test_no_title_with_folder(self):
        m = extract_metadata("1080p.mkv", folder_name="The Matrix (1999)")
        assert m.title == "The Matrix"
