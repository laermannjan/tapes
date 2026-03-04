import xml.etree.ElementTree as ET
from pathlib import Path


def scan_for_nfo_id(video_path: Path) -> tuple[str, int] | None:
    """
    Look for a TMDB or IMDB ID in NFO files near the video.
    Searches: same directory, one level up, two levels up (for tvshow.nfo).
    Returns ("tmdb", id) or ("imdb", id) or None.
    """
    search_dirs = [
        video_path.parent,
        video_path.parent.parent,
        video_path.parent.parent.parent,
    ]

    for directory in search_dirs:
        if not directory.exists():
            continue
        for nfo_file in directory.glob("*.nfo"):
            result = _parse_nfo(nfo_file)
            if result:
                return result

    return None


def _parse_nfo(nfo_path: Path) -> tuple[str, int] | None:
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
    except ET.ParseError:
        return None

    # <tmdbid>438631</tmdbid>
    for tag in ("tmdbid", "tmdb_id", "tmdb"):
        node = root.find(tag)
        if node is not None and node.text:
            try:
                return ("tmdb", int(node.text.strip()))
            except ValueError:
                pass

    # <uniqueid type="tmdb">438631</uniqueid>
    for node in root.findall("uniqueid"):
        id_type = node.get("type", "").lower()
        if id_type == "tmdb" and node.text:
            try:
                return ("tmdb", int(node.text.strip()))
            except ValueError:
                pass

    return None
