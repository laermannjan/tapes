from pathlib import Path

try:
    from pymediainfo import MediaInfo
    MEDIAINFO_AVAILABLE = True
except Exception:
    MEDIAINFO_AVAILABLE = False


def parse_mediainfo(path) -> dict:
    """
    Extract technical metadata from a media file.
    Returns {} if pymediainfo is unavailable or the file cannot be parsed.
    MediaInfo values take precedence over guessit for technical fields.
    """
    if not MEDIAINFO_AVAILABLE:
        return {}

    try:
        info = MediaInfo.parse(str(path))
    except Exception:
        return {}

    result = {}
    for track in info.tracks:
        if track.track_type == "Video":
            result.update(_parse_video_track(track))
        elif track.track_type == "Audio" and "audio" not in result:
            result["audio"] = (
                getattr(track, "commercial_name", None)
                or getattr(track, "format", None)
            )
        elif track.track_type == "General":
            title = getattr(track, "title", None) or getattr(track, "movie_name", None)
            if title:
                result["embedded_title"] = title

    return result


def _parse_video_track(track) -> dict:
    out = {}
    height = getattr(track, "height", None)
    if height:
        if height >= 2160:
            out["resolution"] = "2160p"
        elif height >= 1080:
            out["resolution"] = "1080p"
        elif height >= 720:
            out["resolution"] = "720p"
        else:
            out["resolution"] = f"{height}p"

    codec_id = getattr(track, "codec_id", None) or getattr(track, "format", None)
    if codec_id:
        out["codec"] = codec_id

    hdr = getattr(track, "hdr_format", None) or getattr(track, "transfer_characteristics", None)
    out["hdr"] = 1 if hdr else 0

    return out
