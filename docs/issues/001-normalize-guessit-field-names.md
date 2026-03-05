# Issue 001: Normalize guessit field names in parse_filename

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this fix.

**Bug:** guessit returns `video_codec` for the codec field and `source` for the
media source (e.g. "Blu-ray", "WEB-DL"). Downstream code in
`_write_db_record` expects `codec` and uses `file_info.get("source", "tmdb")`
for the DB `match_source` field. This means:
1. `codec` in the DB is always `None` when mediainfo is unavailable (common).
2. `match_source` in the DB gets "Blu-ray" instead of the identification method.

**Fix:** Rename guessit keys in `parse_filename` so downstream code gets
consistent field names without needing to know guessit internals.

**Scope:** This ticket ONLY touches `tapes/identification/filename.py` and its
test file. No other files.

---

## Context

### How guessit fields flow through the system

```
parse_filename()  ->  file_info dict  ->  _write_db_record()
  "video_codec"         stored as-is        reads "codec"       -> None (BUG)
  "source"              stored as-is        reads "source"      -> "Blu-ray" (BUG)
  "screen_size"         stored as-is        reads "screen_size" -> works (has fallback)
```

### Current code (`tapes/identification/filename.py`)

```python
def parse_filename(filename: str, folder_name: str | None = None) -> dict:
    result = dict(guessit(filename))
    # ... normalisation for TV show title ...
    return result
```

guessit returns keys like `video_codec`, `screen_size`, `source`, `audio_codec`.
The dict is returned as-is except for the show/title swap.

### Current consumer (`tapes/importer/service.py:299-332`)

```python
def _write_db_record(self, src, dst, candidate, file_info):
    ...
    codec=file_info.get("codec"),                              # line 322 -- misses "video_codec"
    resolution=file_info.get("resolution") or file_info.get("screen_size"),  # line 323 -- has fallback
    audio=file_info.get("audio"),                              # line 324
    match_source=file_info.get("source", "tmdb"),              # line 325 -- gets "Blu-ray" etc.
```

---

## Files to modify

- **Modify:** `tapes/identification/filename.py:1-24`
- **Test:** `tests/test_identification/test_filename.py`

No other files. Do not touch `service.py`, `pipeline.py`, or any other file.

---

## Step 1: Write failing tests

Add to `tests/test_identification/test_filename.py`:

```python
def test_video_codec_normalised_to_codec():
    """guessit's 'video_codec' key is renamed to 'codec'."""
    r = parse_filename("Dune.2021.2160p.BluRay.x265.mkv")
    assert "codec" in r
    assert "video_codec" not in r


def test_source_renamed_to_media_source():
    """guessit's 'source' key (media source) is renamed to 'media_source'
    so it doesn't collide with the identification source field."""
    r = parse_filename("Dune.2021.2160p.BluRay.x265.mkv")
    assert "media_source" in r
    assert "source" not in r


def test_audio_codec_normalised_to_audio():
    """guessit's 'audio_codec' key is renamed to 'audio'."""
    r = parse_filename("Dune.2021.DTS-HD.BluRay.mkv")
    # audio_codec may or may not be detected depending on guessit version,
    # but if present it should be renamed
    if "audio" in r or "audio_codec" in r:
        assert "audio_codec" not in r
```

## Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_identification/test_filename.py::test_video_codec_normalised_to_codec -v
uv run pytest tests/test_identification/test_filename.py::test_source_renamed_to_media_source -v
```

Expected: FAIL -- `video_codec` and `source` are present, `codec` and `media_source` are not.

## Step 3: Implement

In `tapes/identification/filename.py`, add a key-renaming step after the
existing TV show normalisation (after line 22, before the return):

```python
# Normalise guessit field names to match downstream expectations.
# - "video_codec" -> "codec"    (DB and templates use "codec")
# - "source"      -> "media_source" (avoid collision with identification source)
# - "audio_codec" -> "audio"    (DB uses "audio")
_GUESSIT_RENAMES = {
    "video_codec": "codec",
    "source": "media_source",
    "audio_codec": "audio",
}


def parse_filename(filename: str, folder_name: str | None = None) -> dict:
    result = dict(guessit(filename))

    # If guessit couldn't determine the title, try the folder name
    if not result.get("title") and folder_name:
        folder_result = dict(guessit(folder_name))
        result.setdefault("title", folder_result.get("title"))
        result.setdefault("year", folder_result.get("year"))

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
```

## Step 4: Run all filename tests

```bash
uv run pytest tests/test_identification/test_filename.py -v
```

Expected: ALL PASS. Existing tests that check `screen_size` should still pass
(we don't rename that key -- it's already handled by a fallback in
`_write_db_record`).

## Step 5: Run full test suite

```bash
uv run pytest -x -q
```

Verify no other tests break. The only consumers of `file_info.get("video_codec")`
or `file_info.get("source")` are in `_write_db_record`, which already fails to
find them (that's the bug). So renaming them doesn't change current behavior of
other code -- it fixes it.

## Step 6: Commit

```
fix: normalize guessit field names in parse_filename

- Rename video_codec -> codec so DB record gets the codec value
- Rename source -> media_source to avoid collision with identification source
- Rename audio_codec -> audio for consistency
```

---

## Verification

After this fix, `file_info.get("codec")` in `_write_db_record` will find the
codec value parsed by guessit (when mediainfo is unavailable). The
`media_source` rename prevents guessit's "Blu-ray"/"WEB-DL" from being stored
as `match_source` in the DB (see Issue 002 for the full match_source fix).
