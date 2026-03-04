from unittest.mock import patch, MagicMock
from tapes.identification.mediainfo import parse_mediainfo


def test_returns_empty_when_unavailable(tmp_path):
    f = tmp_path / "test.mkv"
    f.write_bytes(b"fake")
    with patch("tapes.identification.mediainfo.MEDIAINFO_AVAILABLE", False):
        result = parse_mediainfo(f)
    assert result == {}


def test_extracts_video_fields():
    mock_track = MagicMock()
    mock_track.track_type = "Video"
    mock_track.codec_id = "V_MPEGH/ISO/HEVC"
    mock_track.width = 3840
    mock_track.height = 2160
    mock_track.hdr_format = "Dolby Vision"
    mock_track.transfer_characteristics = None

    with patch("tapes.identification.mediainfo.MediaInfo") as MockMI:
        MockMI.parse.return_value.tracks = [mock_track]
        with patch("tapes.identification.mediainfo.MEDIAINFO_AVAILABLE", True):
            result = parse_mediainfo("fake.mkv")

    assert result["resolution"] == "2160p"
    assert result["hdr"] == 1
    assert result["codec"] == "V_MPEGH/ISO/HEVC"


def test_extracts_audio_field():
    video_track = MagicMock()
    video_track.track_type = "Video"
    video_track.codec_id = "avc1"
    video_track.height = 1080
    video_track.hdr_format = None
    video_track.transfer_characteristics = None

    audio_track = MagicMock()
    audio_track.track_type = "Audio"
    audio_track.commercial_name = "Dolby TrueHD"
    audio_track.format = "TrueHD"

    with patch("tapes.identification.mediainfo.MediaInfo") as MockMI:
        MockMI.parse.return_value.tracks = [video_track, audio_track]
        with patch("tapes.identification.mediainfo.MEDIAINFO_AVAILABLE", True):
            result = parse_mediainfo("fake.mkv")

    assert result["audio"] == "Dolby TrueHD"
