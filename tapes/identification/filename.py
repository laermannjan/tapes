from guessit import guessit

_GUESSIT_RENAMES = {
    "video_codec": "codec",
    "source": "media_source",
    "audio_codec": "audio",
}


def parse_filename(filename: str, folder_name: str | None = None) -> dict:
    """
    Parse a filename using guessit, with optional folder name as additional context.
    Returns a dict of fields. 'episode' may be int or list[int] for multi-episode files.
    """
    result = dict(guessit(filename))

    # If guessit couldn't determine the title, try the folder name
    if not result.get("title") and folder_name:
        folder_result = dict(guessit(folder_name))
        result.setdefault("title", folder_result.get("title"))
        result.setdefault("year", folder_result.get("year"))

    # guessit uses 'title' for movies and 'title' for shows too — normalise
    # For TV episodes guessit puts show name in 'title', not 'show'
    if result.get("type") == "episode" and "title" in result and "show" not in result:
        result["show"] = result.pop("title")
        if "episode_title" in result:
            result["episode_title"] = result["episode_title"]

    # Rename guessit keys to match downstream field expectations
    for old_key, new_key in _GUESSIT_RENAMES.items():
        if old_key in result:
            result[new_key] = result.pop(old_key)

    return result
