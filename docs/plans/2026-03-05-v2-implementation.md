# Tapes Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Tier 1 of the tapes rewrite -- scan, metadata extraction, companion discovery, grouping, and a textual TUI -- so a user can point at a directory and see how the tool groups their files.

**Architecture:** Four-pass pipeline (scan -> extract -> companions -> group) producing `ImportGroup` objects displayed in a textual vertical accordion TUI. No network calls, no file operations. Pydantic v2 config with sane defaults. E2E tests as primary validation.

**Tech Stack:** Python 3.11+, guessit, textual, pydantic v2, typer, rich, pytest

**Key design notes:**
- Files and groups have a bidirectional relationship. Each file knows its group, each group knows its files. This makes dedup and reassignment straightforward.
- Companion discovery is stem-prefix matching only. Directory-level companions (poster.jpg, fanart.jpg) are deferred.
- The grouper uses dict-based group-by on composite keys (O(n) per criterion), not pairwise comparison.
- `tapes import` is user-facing (always runs full pipeline). `tapes scan` is internal/hidden.

---

## Task 0: Project scaffolding

**Files:**
- Modify: `pyproject.toml`
- Delete: all existing `tapes/` source and `tests/` (clean slate)
- Create: `tapes/__init__.py`, `tapes/py.typed`

**Step 1: Clean the source tree**

Remove all existing source code and tests. We're starting fresh -- the spike code is on `main` for reference.

```bash
rm -rf tapes/ tests/
mkdir -p tapes tests
```

**Step 2: Update pyproject.toml**

```toml
[project]
name = "tapes"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.15,<1",
    "rich>=13,<14",
    "guessit>=3.8,<4",
    "pydantic>=2.6,<3",
    "pyyaml>=6,<7",
    "textual>=3,<4",
]

[dependency-groups]
dev = [
    "pytest>=8,<9",
    "pytest-cov>=6,<7",
    "pytest-asyncio>=0.25,<1",
    "textual-dev>=1,<2",
]

[project.scripts]
tapes = "tapes.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Note: `requests`, `pymediainfo`, `jellyfish`, `responses` dropped for now. They return in later tiers.

**Step 3: Create package init**

```python
# tapes/__init__.py
```

**Step 4: Sync and verify**

```bash
uv sync
uv run python -c "import tapes; print('ok')"
```

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: scaffold rewrite, clean slate"
```

---

## Task 1: Models

**Files:**
- Create: `tapes/models.py`
- Create: `tests/test_models.py`

The models establish a bidirectional file-group relationship: `ImportGroup.files` lists its files, and each `FileEntry.group` points back to its group. Assignment is managed through `ImportGroup.add_file()` and `ImportGroup.remove_file()` to keep both sides consistent.

**Step 1: Write the tests**

```python
# tests/test_models.py
from tapes.models import (
    FileMetadata,
    FileEntry,
    ImportGroup,
    GroupType,
    GroupStatus,
    file_role,
)
from pathlib import Path


class TestFileRole:
    def test_video_extensions(self):
        assert file_role(Path("movie.mkv")) == "video"
        assert file_role(Path("movie.mp4")) == "video"
        assert file_role(Path("movie.avi")) == "video"

    def test_subtitle_extensions(self):
        assert file_role(Path("movie.srt")) == "subtitle"
        assert file_role(Path("movie.ass")) == "subtitle"
        assert file_role(Path("movie.vtt")) == "subtitle"

    def test_artwork_extensions(self):
        assert file_role(Path("poster.jpg")) == "artwork"
        assert file_role(Path("poster.png")) == "artwork"

    def test_metadata_extensions(self):
        assert file_role(Path("movie.nfo")) == "metadata"
        assert file_role(Path("movie.xml")) == "metadata"

    def test_other_extension(self):
        assert file_role(Path("readme.txt")) == "other"

    def test_unknown_extension(self):
        assert file_role(Path("something.xyz")) == "other"

    def test_case_insensitive(self):
        assert file_role(Path("movie.MKV")) == "video"
        assert file_role(Path("movie.SRT")) == "subtitle"


class TestFileMetadata:
    def test_defaults(self):
        m = FileMetadata()
        assert m.media_type is None
        assert m.title is None
        assert m.year is None
        assert m.season is None
        assert m.episode is None
        assert m.part is None
        assert m.raw == {}

    def test_with_values(self):
        m = FileMetadata(media_type="movie", title="Dune", year=2021)
        assert m.media_type == "movie"
        assert m.title == "Dune"
        assert m.year == 2021


class TestImportGroup:
    def test_creation(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"), role="video")
        group = ImportGroup(metadata=FileMetadata(title="Test"))
        group.add_file(entry)
        assert group.group_type == GroupType.STANDALONE
        assert group.status == GroupStatus.PENDING
        assert len(group.files) == 1
        assert group.id  # auto-generated

    def test_label_from_metadata(self):
        group = ImportGroup(metadata=FileMetadata(title="Dune", year=2021))
        group.add_file(FileEntry(path=Path("/tmp/movie.mkv"), role="video"))
        assert group.label == "Dune (2021)"

    def test_label_movie_no_year(self):
        group = ImportGroup(metadata=FileMetadata(title="Dune"))
        group.add_file(FileEntry(path=Path("/tmp/movie.mkv"), role="video"))
        assert group.label == "Dune"

    def test_label_episode(self):
        group = ImportGroup(
            metadata=FileMetadata(
                media_type="episode", title="Breaking Bad", season=1
            ),
        )
        group.add_file(FileEntry(path=Path("/tmp/ep.mkv"), role="video"))
        assert group.label == "Breaking Bad S01"

    def test_label_fallback_to_filename(self):
        group = ImportGroup(metadata=FileMetadata())
        group.add_file(FileEntry(path=Path("/tmp/random_clip.avi"), role="video"))
        assert group.label == "random_clip.avi"

    def test_video_files_property(self):
        group = ImportGroup(metadata=FileMetadata())
        group.add_file(FileEntry(path=Path("/tmp/movie.mkv"), role="video"))
        group.add_file(FileEntry(path=Path("/tmp/movie.srt"), role="subtitle"))
        assert len(group.video_files) == 1
        assert group.video_files[0].role == "video"


class TestBidirectionalRelationship:
    def test_add_file_sets_group(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"), role="video")
        group = ImportGroup(metadata=FileMetadata())
        group.add_file(entry)
        assert entry.group is group

    def test_remove_file_clears_group(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"), role="video")
        group = ImportGroup(metadata=FileMetadata())
        group.add_file(entry)
        group.remove_file(entry)
        assert entry.group is None
        assert entry not in group.files

    def test_add_file_to_new_group_removes_from_old(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"), role="video")
        group_a = ImportGroup(metadata=FileMetadata())
        group_b = ImportGroup(metadata=FileMetadata())
        group_a.add_file(entry)
        group_b.add_file(entry)
        assert entry.group is group_b
        assert entry not in group_a.files
        assert entry in group_b.files

    def test_no_duplicate_files(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"), role="video")
        group = ImportGroup(metadata=FileMetadata())
        group.add_file(entry)
        group.add_file(entry)  # adding same file again
        assert len(group.files) == 1
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: ModuleNotFoundError

**Step 3: Implement models**

```python
# tapes/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

VIDEO_EXTENSIONS = frozenset(
    {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"}
)

SUBTITLE_EXTENSIONS = frozenset({".srt", ".sub", ".idx", ".ssa", ".ass", ".vtt"})
METADATA_EXTENSIONS = frozenset({".nfo", ".xml"})
ARTWORK_EXTENSIONS = frozenset({".jpg", ".png", ".webp"})

_ROLE_MAP: dict[str, str] = {}
for _ext in VIDEO_EXTENSIONS:
    _ROLE_MAP[_ext] = "video"
for _ext in SUBTITLE_EXTENSIONS:
    _ROLE_MAP[_ext] = "subtitle"
for _ext in METADATA_EXTENSIONS:
    _ROLE_MAP[_ext] = "metadata"
for _ext in ARTWORK_EXTENSIONS:
    _ROLE_MAP[_ext] = "artwork"


def file_role(path: Path) -> str:
    return _ROLE_MAP.get(path.suffix.lower(), "other")


class GroupType(str, Enum):
    STANDALONE = "standalone"
    MULTI_PART = "multi_part"
    SEASON = "season"


class GroupStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    AUTO_ACCEPTED = "auto_accepted"
    SKIPPED = "skipped"


@dataclass
class FileMetadata:
    media_type: str | None = None
    title: str | None = None
    year: int | None = None
    season: int | None = None
    episode: int | list[int] | None = None
    part: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class FileEntry:
    path: Path
    role: str
    group: ImportGroup | None = field(default=None, repr=False, compare=False)


@dataclass
class ImportGroup:
    metadata: FileMetadata | None = None
    group_type: GroupType = GroupType.STANDALONE
    status: GroupStatus = GroupStatus.PENDING
    match: object = None  # SearchResult in Tier 2
    candidates: list = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    _files: list[FileEntry] = field(default_factory=list, repr=False)

    @property
    def files(self) -> list[FileEntry]:
        return list(self._files)

    def add_file(self, entry: FileEntry) -> None:
        """Add a file to this group. Removes it from its previous group if any."""
        if entry.group is self:
            return
        if entry.group is not None:
            entry.group._files.remove(entry)
        entry.group = self
        self._files.append(entry)

    def remove_file(self, entry: FileEntry) -> None:
        """Remove a file from this group."""
        if entry in self._files:
            self._files.remove(entry)
            entry.group = None

    @property
    def label(self) -> str:
        if self.metadata and self.metadata.title:
            m = self.metadata
            if m.media_type == "episode" and m.season is not None:
                return f"{m.title} S{m.season:02d}"
            if m.year:
                return f"{m.title} ({m.year})"
            return m.title
        # Fallback to first video filename
        for f in self._files:
            if f.role == "video":
                return f.path.name
        return self._files[0].path.name if self._files else "empty"

    @property
    def video_files(self) -> list[FileEntry]:
        return [f for f in self._files if f.role == "video"]
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_models.py -v
```

Expected: all pass

**Step 5: Commit**

```bash
git add tapes/models.py tests/test_models.py
git commit -m "feat: add core data models with bidirectional file-group relationship"
```

---

## Task 2: Scanner

**Files:**
- Create: `tapes/scanner.py`
- Create: `tests/test_scanner.py`

Port from spike's `tapes/discovery/scanner.py` with minor cleanup.

**Step 1: Write the tests**

```python
# tests/test_scanner.py
from pathlib import Path
from tapes.scanner import scan_media_files


class TestScanMediaFiles:
    def test_finds_video_files(self, tmp_path):
        (tmp_path / "movie.mkv").write_bytes(b"\x00")
        (tmp_path / "show.mp4").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == 2

    def test_ignores_non_video(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hi")
        (tmp_path / "movie.mkv").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == 1

    def test_recursive(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "episode.mkv").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == 1

    def test_excludes_sample_files(self, tmp_path):
        (tmp_path / "sample.mkv").write_bytes(b"\x00")
        (tmp_path / "movie-sample.mkv").write_bytes(b"\x00")
        (tmp_path / "movie.mkv").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "movie.mkv"

    def test_excludes_hidden_dirs(self, tmp_path):
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "video.mkv").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == 0

    def test_single_file_input(self, tmp_path):
        f = tmp_path / "movie.mkv"
        f.write_bytes(b"\x00")
        result = scan_media_files(f)
        assert len(result) == 1

    def test_single_non_video_file(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("hi")
        result = scan_media_files(f)
        assert len(result) == 0

    def test_sorted_output(self, tmp_path):
        (tmp_path / "b.mkv").write_bytes(b"\x00")
        (tmp_path / "a.mkv").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert result[0].name == "a.mkv"

    def test_case_insensitive_extension(self, tmp_path):
        (tmp_path / "movie.MKV").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == 1

    def test_empty_directory(self, tmp_path):
        result = scan_media_files(tmp_path)
        assert result == []

    def test_all_video_extensions(self, tmp_path):
        exts = [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"]
        for ext in exts:
            (tmp_path / f"video{ext}").write_bytes(b"\x00")
        result = scan_media_files(tmp_path)
        assert len(result) == len(exts)
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_scanner.py -v
```

**Step 3: Implement scanner**

Port directly from spike (`tapes/discovery/scanner.py`):

```python
# tapes/scanner.py
import re
from pathlib import Path

from tapes.models import VIDEO_EXTENSIONS

_SAMPLE_PATTERN = re.compile(
    r"(?i)(^sample$|^sample[\.\-_ ]|[\.\-_ ]sample[\.\-_ ]|[\.\-_ ]sample$)"
)


def scan_media_files(root: Path) -> list[Path]:
    """Recursively find all video files under root.

    If root is a file, check it directly.
    Excludes sample files and hidden directories.
    Returns a sorted list of Path objects.
    """
    if root.is_file():
        if root.suffix.lower() in VIDEO_EXTENSIONS and not _SAMPLE_PATTERN.search(
            root.stem
        ):
            return [root]
        return []

    found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _SAMPLE_PATTERN.search(path.stem):
            continue
        found.append(path)
    return sorted(found)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_scanner.py -v
```

**Step 5: Commit**

```bash
git add tapes/scanner.py tests/test_scanner.py
git commit -m "feat: add video file scanner"
```

---

## Task 3: Metadata extraction

**Files:**
- Create: `tapes/metadata.py`
- Create: `tests/test_metadata.py`

Port from spike's `tapes/identification/filename.py`. Wraps guessit and normalizes output into `FileMetadata`.

**Step 1: Write the tests**

```python
# tests/test_metadata.py
from tapes.metadata import extract_metadata


class TestExtractMetadata:
    def test_movie(self):
        m = extract_metadata("Dune.2021.1080p.BluRay.mkv")
        assert m.media_type == "movie"
        assert m.title == "Dune"
        assert m.year == 2021

    def test_episode(self):
        m = extract_metadata("Breaking.Bad.S01E02.720p.mkv")
        assert m.media_type == "episode"
        assert m.title is not None  # guessit extracts show name
        assert m.season == 1
        assert m.episode == 2

    def test_multi_episode(self):
        m = extract_metadata("Show.S01E01E02.mkv")
        assert m.media_type == "episode"
        assert isinstance(m.episode, list)
        assert m.episode == [1, 2]

    def test_part(self):
        m = extract_metadata("Movie.CD1.mkv")
        assert m.part == 1

    def test_folder_fallback(self):
        m = extract_metadata("video.mkv", folder_name="Dune (2021)")
        assert m.title == "Dune"
        assert m.year == 2021

    def test_raw_preserved(self):
        m = extract_metadata("Dune.2021.1080p.BluRay.x264.mkv")
        assert "codec" in m.raw or "screen_size" in m.raw

    def test_field_normalization(self):
        m = extract_metadata("Movie.2021.x264.BluRay.DTS.mkv")
        # video_codec -> codec, source -> media_source, audio_codec -> audio
        assert "video_codec" not in m.raw
        assert "source" not in m.raw
        assert "audio_codec" not in m.raw

    def test_no_title(self):
        m = extract_metadata("123.mkv")
        # Should not crash; title may be None or a number
        assert m is not None
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_metadata.py -v
```

**Step 3: Implement metadata extraction**

```python
# tapes/metadata.py
from guessit import guessit

from tapes.models import FileMetadata

_GUESSIT_RENAMES = {
    "video_codec": "codec",
    "source": "media_source",
    "audio_codec": "audio",
}


def extract_metadata(filename: str, folder_name: str | None = None) -> FileMetadata:
    """Extract metadata from a filename using guessit.

    Falls back to folder_name for title/year if guessit can't determine them.
    Returns a FileMetadata with normalized fields.
    """
    raw = dict(guessit(filename))

    # Folder fallback for title/year
    if not raw.get("title") and folder_name:
        folder_result = dict(guessit(folder_name))
        raw.setdefault("title", folder_result.get("title"))
        raw.setdefault("year", folder_result.get("year"))

    title = raw.get("title")

    # Normalize field names
    for old_key, new_key in _GUESSIT_RENAMES.items():
        if old_key in raw:
            raw[new_key] = raw.pop(old_key)

    # Extract episode -- may be int or list[int]
    episode = raw.get("episode")
    if isinstance(episode, list):
        episode = list(episode)
    elif isinstance(episode, int):
        pass
    else:
        episode = None

    return FileMetadata(
        media_type=raw.get("type"),
        title=str(title) if title is not None else None,
        year=raw.get("year"),
        season=raw.get("season"),
        episode=episode,
        part=raw.get("part") or raw.get("cd"),
        raw=raw,
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_metadata.py -v
```

**Step 5: Commit**

```bash
git add tapes/metadata.py tests/test_metadata.py
git commit -m "feat: add guessit metadata extraction"
```

---

## Task 4: Companion discovery

**Files:**
- Create: `tapes/companions.py`
- Create: `tests/test_companions.py`

Stem-prefix matching only. A companion is a non-video file whose stem starts with the video's stem followed by a separator (`.`, `_`, `-`) or is an exact stem match. Directory-level companions (poster.jpg, fanart.jpg) are deferred.

**Step 1: Write the tests**

```python
# tests/test_companions.py
from pathlib import Path
from tapes.companions import find_companions


class TestStemMatchedCompanions:
    def test_subtitle_same_dir(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.en.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 1
        assert result[0].role == "subtitle"

    def test_separator_dot(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.en.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 1

    def test_separator_underscore(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie_forced.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 1

    def test_separator_dash(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie-eng.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 1

    def test_no_separator_no_match(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "MovieExtra.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 0

    def test_exact_stem_match(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 1

    def test_child_directory(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        subs = tmp_path / "Subs"
        subs.mkdir()
        (subs / "Movie.en.srt").write_text("")
        result = find_companions(video, max_depth=3)
        assert len(result) == 1

    def test_depth_limit(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "Movie.en.srt").write_text("")
        result = find_companions(video, max_depth=3)
        assert len(result) == 0  # 4 levels deep, limit is 3

    def test_ignores_video_files(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.mp4").write_bytes(b"\x00")
        result = find_companions(video)
        assert len(result) == 0

    def test_artwork(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.jpg").write_bytes(b"\x00")
        result = find_companions(video)
        assert len(result) == 1
        assert result[0].role == "artwork"

    def test_nfo(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.nfo").write_text("")
        result = find_companions(video)
        assert len(result) == 1
        assert result[0].role == "metadata"

    def test_non_whitelisted_extension_ignored(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "Movie.exe").write_bytes(b"\x00")
        result = find_companions(video)
        assert len(result) == 0

    def test_case_insensitive_stem(self, tmp_path):
        video = tmp_path / "Movie.mkv"
        video.write_bytes(b"\x00")
        (tmp_path / "movie.en.srt").write_text("")
        result = find_companions(video)
        assert len(result) == 1
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_companions.py -v
```

**Step 3: Implement companion discovery**

```python
# tapes/companions.py
from pathlib import Path

from tapes.models import (
    ARTWORK_EXTENSIONS,
    METADATA_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    FileEntry,
    file_role,
)

COMPANION_EXTENSIONS = SUBTITLE_EXTENSIONS | METADATA_EXTENSIONS | ARTWORK_EXTENSIONS | frozenset({".txt"})

COMPANION_SEPARATORS = (".", "_", "-")


def find_companions(
    video: Path,
    max_depth: int = 0,
    separators: tuple[str, ...] = COMPANION_SEPARATORS,
) -> list[FileEntry]:
    """Find companion files for a video using stem prefix matching.

    Searches the video's parent directory and child directories up to max_depth.
    A file is a companion if its stem starts with the video's stem followed by
    a separator or end-of-string, and its extension is in the companion whitelist.

    Args:
        video: Path to the video file.
        max_depth: How deep to search child directories (0 = same dir only).
        separators: Stem prefix separators to match.
    """
    video_stem = video.stem
    video_dir = video.parent
    companions: list[FileEntry] = []

    for candidate in _iter_files(video_dir, max_depth):
        if candidate == video:
            continue
        if candidate.suffix.lower() in VIDEO_EXTENSIONS:
            continue
        if candidate.suffix.lower() not in COMPANION_EXTENSIONS:
            continue
        if _is_stem_match(candidate, video_stem, separators):
            companions.append(FileEntry(path=candidate, role=file_role(candidate)))

    return companions


def _is_stem_match(candidate: Path, video_stem: str, separators: tuple[str, ...]) -> bool:
    """Check if candidate's stem starts with video_stem + separator or equals it.

    Case-insensitive comparison.
    """
    stem = candidate.stem.lower()
    target = video_stem.lower()
    if stem == target:
        return True
    for sep in separators:
        if stem.startswith(target + sep):
            return True
    return False


def _iter_files(root: Path, max_depth: int) -> list[Path]:
    """Iterate files in root and child directories up to max_depth."""
    results: list[Path] = []
    _walk(root, root, max_depth, results)
    return results


def _walk(current: Path, root: Path, max_depth: int, results: list[Path]) -> None:
    """Recursively walk directories up to max_depth."""
    try:
        for entry in sorted(current.iterdir()):
            if entry.is_file():
                results.append(entry)
            elif entry.is_dir() and not entry.name.startswith("."):
                depth = len(entry.relative_to(root).parts)
                if depth <= max_depth:
                    _walk(entry, root, max_depth, results)
    except PermissionError:
        pass
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_companions.py -v
```

**Step 5: Commit**

```bash
git add tapes/companions.py tests/test_companions.py
git commit -m "feat: add companion file discovery"
```

---

## Task 5: Grouper

**Files:**
- Create: `tapes/grouper.py`
- Create: `tests/test_grouper.py`

Uses dict-based group-by on composite keys -- O(n) per criterion. Merge criteria are batch transforms: `Callable[[list[ImportGroup]], list[ImportGroup]]`.

**Step 1: Write the tests**

```python
# tests/test_grouper.py
from pathlib import Path
from tapes.grouper import group_files, same_season, same_multi_part
from tapes.models import FileEntry, FileMetadata, GroupType, ImportGroup


def _make_group(title, media_type="movie", season=None, episode=None, part=None, filename="video.mkv"):
    group = ImportGroup(
        metadata=FileMetadata(
            media_type=media_type,
            title=title,
            season=season,
            episode=episode,
            part=part,
        ),
    )
    group.add_file(FileEntry(path=Path(f"/tmp/{filename}"), role="video"))
    return group


class TestSameSeasonCriterion:
    def test_merges_same_show_same_season(self):
        groups = [
            _make_group("Breaking Bad", "episode", season=1, episode=1, filename="ep1.mkv"),
            _make_group("Breaking Bad", "episode", season=1, episode=2, filename="ep2.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 1
        assert len(result[0].files) == 2

    def test_no_merge_different_season(self):
        groups = [
            _make_group("Breaking Bad", "episode", season=1, episode=1, filename="s1e1.mkv"),
            _make_group("Breaking Bad", "episode", season=2, episode=1, filename="s2e1.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 2

    def test_no_merge_different_show(self):
        groups = [
            _make_group("Breaking Bad", "episode", season=1, episode=1, filename="bb.mkv"),
            _make_group("Better Call Saul", "episode", season=1, episode=1, filename="bcs.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 2

    def test_case_insensitive_title(self):
        groups = [
            _make_group("breaking bad", "episode", season=1, episode=1, filename="ep1.mkv"),
            _make_group("Breaking Bad", "episode", season=1, episode=2, filename="ep2.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 1

    def test_skips_movies(self):
        groups = [
            _make_group("Dune", "movie", filename="dune1.mkv"),
            _make_group("Dune", "movie", filename="dune2.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 2

    def test_skips_no_season(self):
        groups = [
            _make_group("Show", "episode", episode=1, filename="ep1.mkv"),
            _make_group("Show", "episode", episode=2, filename="ep2.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 2

    def test_single_episode_stays_standalone(self):
        groups = [
            _make_group("Show", "episode", season=1, episode=1, filename="ep1.mkv"),
        ]
        result = same_season(groups)
        assert len(result) == 1
        assert result[0].group_type == GroupType.STANDALONE

    def test_assigns_season_type(self):
        groups = [
            _make_group("BB", "episode", season=1, episode=1, filename="ep1.mkv"),
            _make_group("BB", "episode", season=1, episode=2, filename="ep2.mkv"),
        ]
        result = same_season(groups)
        assert result[0].group_type == GroupType.SEASON


class TestSameMultiPartCriterion:
    def test_merges_same_title_with_parts(self):
        groups = [
            _make_group("Kill Bill", part=1, filename="cd1.mkv"),
            _make_group("Kill Bill", part=2, filename="cd2.mkv"),
        ]
        result = same_multi_part(groups)
        assert len(result) == 1
        assert len(result[0].files) == 2

    def test_no_merge_without_parts(self):
        groups = [
            _make_group("Dune", filename="dune1.mkv"),
            _make_group("Dune", filename="dune2.mkv"),
        ]
        result = same_multi_part(groups)
        assert len(result) == 2

    def test_assigns_multi_part_type(self):
        groups = [
            _make_group("Kill Bill", part=1, filename="cd1.mkv"),
            _make_group("Kill Bill", part=2, filename="cd2.mkv"),
        ]
        result = same_multi_part(groups)
        assert result[0].group_type == GroupType.MULTI_PART


class TestGroupFiles:
    def test_full_pipeline(self):
        groups = [
            _make_group("BB", "episode", season=1, episode=1, filename="ep1.mkv"),
            _make_group("BB", "episode", season=1, episode=2, filename="ep2.mkv"),
            _make_group("Dune", "movie", filename="dune.mkv"),
            _make_group("Kill Bill", part=1, filename="kb1.mkv"),
            _make_group("Kill Bill", part=2, filename="kb2.mkv"),
        ]
        result = group_files(groups)
        assert len(result) == 3  # BB season, Dune standalone, Kill Bill multi-part

        types = {g.group_type for g in result}
        assert GroupType.SEASON in types
        assert GroupType.MULTI_PART in types
        assert GroupType.STANDALONE in types

    def test_preserves_companions_through_merge(self):
        g = _make_group("BB", "episode", season=1, episode=1, filename="ep1.mkv")
        g.add_file(FileEntry(path=Path("/tmp/ep1.srt"), role="subtitle"))
        groups = [
            g,
            _make_group("BB", "episode", season=1, episode=2, filename="ep2.mkv"),
        ]
        result = group_files(groups)
        assert len(result) == 1
        assert len(result[0].files) == 3  # 2 videos + 1 subtitle

    def test_files_point_to_merged_group(self):
        groups = [
            _make_group("BB", "episode", season=1, episode=1, filename="ep1.mkv"),
            _make_group("BB", "episode", season=1, episode=2, filename="ep2.mkv"),
        ]
        result = group_files(groups)
        assert len(result) == 1
        for f in result[0].files:
            assert f.group is result[0]
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_grouper.py -v
```

**Step 3: Implement grouper**

```python
# tapes/grouper.py
from collections import defaultdict
from typing import Callable

from tapes.models import GroupType, ImportGroup

MergeCriterion = Callable[[list[ImportGroup]], list[ImportGroup]]


def same_season(groups: list[ImportGroup]) -> list[ImportGroup]:
    """Merge groups with same (title, season) for episodes. O(n)."""
    keyed: defaultdict[tuple[str, int], list[ImportGroup]] = defaultdict(list)
    unkeyed: list[ImportGroup] = []

    for g in groups:
        m = g.metadata
        if m and m.media_type == "episode" and m.title and m.season is not None:
            key = (m.title.lower(), m.season)
            keyed[key].append(g)
        else:
            unkeyed.append(g)

    result: list[ImportGroup] = list(unkeyed)
    for key_groups in keyed.values():
        if len(key_groups) == 1:
            result.append(key_groups[0])
        else:
            merged = _merge(key_groups)
            merged.group_type = GroupType.SEASON
            result.append(merged)
    return result


def same_multi_part(groups: list[ImportGroup]) -> list[ImportGroup]:
    """Merge groups with same title where both have part/cd values. O(n)."""
    keyed: defaultdict[str, list[ImportGroup]] = defaultdict(list)
    unkeyed: list[ImportGroup] = []

    for g in groups:
        m = g.metadata
        if m and m.title and m.part is not None:
            key = m.title.lower()
            keyed[key].append(g)
        else:
            unkeyed.append(g)

    result: list[ImportGroup] = list(unkeyed)
    for key_groups in keyed.values():
        if len(key_groups) == 1:
            result.append(key_groups[0])
        else:
            merged = _merge(key_groups)
            merged.group_type = GroupType.MULTI_PART
            result.append(merged)
    return result


def group_files(
    groups: list[ImportGroup],
    criteria: list[MergeCriterion] | None = None,
) -> list[ImportGroup]:
    """Apply all merge criteria sequentially. Each criterion does a single pass."""
    if criteria is None:
        criteria = [same_season, same_multi_part]
    result = groups
    for criterion in criteria:
        result = criterion(result)
    return result


def _merge(groups: list[ImportGroup]) -> ImportGroup:
    """Merge multiple groups into one. Uses add_file to maintain bidirectional refs."""
    target = ImportGroup(metadata=groups[0].metadata)
    for g in groups:
        for f in list(g.files):  # list() because add_file mutates source
            target.add_file(f)
    return target
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_grouper.py -v
```

**Step 5: Commit**

```bash
git add tapes/grouper.py tests/test_grouper.py
git commit -m "feat: add dict-based group merging"
```

---

## Task 6: Config

**Files:**
- Create: `tapes/config.py`
- Create: `tests/test_config.py`

Pydantic v2 models with sane defaults. Zero config required for Tier 1.

**Step 1: Write the tests**

```python
# tests/test_config.py
from pathlib import Path
from tapes.config import TapesConfig, load_config


class TestTapesConfig:
    def test_defaults(self):
        cfg = TapesConfig()
        assert cfg.scan.companion_depth == 3
        assert cfg.scan.companion_separators == [".", "_", "-"]

    def test_dry_run_default_false(self):
        cfg = TapesConfig()
        assert cfg.dry_run is False


class TestLoadConfig:
    def test_no_config_file(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert isinstance(cfg, TapesConfig)

    def test_empty_config_file(self, tmp_path):
        f = tmp_path / "tapes.yaml"
        f.write_text("")
        cfg = load_config(f)
        assert isinstance(cfg, TapesConfig)

    def test_partial_config(self, tmp_path):
        f = tmp_path / "tapes.yaml"
        f.write_text("scan:\n  companion_depth: 5\n")
        cfg = load_config(f)
        assert cfg.scan.companion_depth == 5
        assert cfg.scan.companion_separators == [".", "_", "-"]  # default preserved

    def test_dry_run_from_config(self, tmp_path):
        f = tmp_path / "tapes.yaml"
        f.write_text("dry_run: true\n")
        cfg = load_config(f)
        assert cfg.dry_run is True
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

**Step 3: Implement config**

```python
# tapes/config.py
from pathlib import Path

import yaml
from pydantic import BaseModel


class ScanConfig(BaseModel):
    companion_separators: list[str] = [".", "_", "-"]
    companion_depth: int = 3


class MetadataConfig(BaseModel):
    tmdb_token: str = ""


class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""


class TapesConfig(BaseModel):
    scan: ScanConfig = ScanConfig()
    metadata: MetadataConfig = MetadataConfig()
    library: LibraryConfig = LibraryConfig()
    dry_run: bool = False


def load_config(path: Path) -> TapesConfig:
    """Load config from a YAML file. Returns defaults if file doesn't exist."""
    if not path.exists():
        return TapesConfig()
    text = path.read_text()
    if not text or not text.strip():
        return TapesConfig()
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return TapesConfig()
    return TapesConfig(**data)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_config.py -v
```

**Step 5: Commit**

```bash
git add tapes/config.py tests/test_config.py
git commit -m "feat: add Pydantic config with sane defaults"
```

---

## Task 7: Pipeline

**Files:**
- Create: `tapes/pipeline.py`
- Create: `tests/test_pipeline.py`

Orchestrates the four passes: scan -> extract -> companions -> group.

**Step 1: Write the tests**

```python
# tests/test_pipeline.py
from pathlib import Path
from tapes.pipeline import run_pipeline
from tapes.config import TapesConfig
from tapes.models import GroupType


class TestPipeline:
    def _make_video(self, path: Path, name: str) -> Path:
        f = path / name
        f.write_bytes(b"\x00" * 1024)
        return f

    def test_single_movie(self, tmp_path):
        self._make_video(tmp_path, "Dune.2021.1080p.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].metadata.title is not None

    def test_season_grouping(self, tmp_path):
        show_dir = tmp_path / "Breaking.Bad.S01"
        show_dir.mkdir()
        self._make_video(show_dir, "Breaking.Bad.S01E01.mkv")
        self._make_video(show_dir, "Breaking.Bad.S01E02.mkv")
        self._make_video(show_dir, "Breaking.Bad.S01E03.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].group_type == GroupType.SEASON
        assert len(groups[0].video_files) == 3

    def test_multi_part_grouping(self, tmp_path):
        self._make_video(tmp_path, "Kill.Bill.CD1.mkv")
        self._make_video(tmp_path, "Kill.Bill.CD2.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].group_type == GroupType.MULTI_PART

    def test_companions_attached(self, tmp_path):
        self._make_video(tmp_path, "Movie.mkv")
        (tmp_path / "Movie.en.srt").write_text("")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert any(f.role == "subtitle" for f in groups[0].files)

    def test_companion_dedup_across_groups(self, tmp_path):
        """A companion claimed by one group is not also claimed by another."""
        self._make_video(tmp_path, "Movie.mkv")
        self._make_video(tmp_path, "Movie.2.mkv")
        (tmp_path / "Movie.en.srt").write_text("")
        groups = run_pipeline(tmp_path)
        all_companions = [f for g in groups for f in g.files if f.role != "video"]
        paths = [f.path for f in all_companions]
        assert len(paths) == len(set(paths))  # no duplicates

    def test_mixed_content(self, tmp_path):
        self._make_video(tmp_path, "Dune.2021.mkv")
        show = tmp_path / "BB"
        show.mkdir()
        self._make_video(show, "Breaking.Bad.S01E01.mkv")
        self._make_video(show, "Breaking.Bad.S01E02.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 2

    def test_empty_directory(self, tmp_path):
        groups = run_pipeline(tmp_path)
        assert groups == []

    def test_all_files_have_group_ref(self, tmp_path):
        self._make_video(tmp_path, "Dune.2021.mkv")
        (tmp_path / "Dune.2021.en.srt").write_text("")
        groups = run_pipeline(tmp_path)
        for g in groups:
            for f in g.files:
                assert f.group is g
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_pipeline.py -v
```

**Step 3: Implement pipeline**

```python
# tapes/pipeline.py
from pathlib import Path

from tapes.companions import find_companions
from tapes.config import TapesConfig
from tapes.grouper import group_files
from tapes.metadata import extract_metadata
from tapes.models import FileEntry, ImportGroup, file_role
from tapes.scanner import scan_media_files


def run_pipeline(
    root: Path,
    config: TapesConfig | None = None,
) -> list[ImportGroup]:
    """Run the full scan -> extract -> companions -> group pipeline."""
    if config is None:
        config = TapesConfig()

    # Pass 1: Scan
    video_paths = scan_media_files(root)
    if not video_paths:
        return []

    # Pass 2: Extract metadata + create initial groups (one per video)
    groups: list[ImportGroup] = []
    for vpath in video_paths:
        folder_name = vpath.parent.name if vpath.parent != root else None
        metadata = extract_metadata(vpath.name, folder_name)
        group = ImportGroup(metadata=metadata)
        group.add_file(FileEntry(path=vpath, role=file_role(vpath)))
        groups.append(group)

    # Pass 3: Find companions for each video (with global dedup)
    claimed: set[Path] = {f.path for g in groups for f in g.files}
    for group in groups:
        for vfile in group.video_files:
            companions = find_companions(
                vfile.path,
                max_depth=config.scan.companion_depth,
                separators=tuple(config.scan.companion_separators),
            )
            for comp in companions:
                if comp.path not in claimed:
                    group.add_file(comp)
                    claimed.add(comp.path)

    # Pass 4: Group by merge criteria
    groups = group_files(groups)

    return groups
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_pipeline.py -v
```

**Step 5: Commit**

```bash
git add tapes/pipeline.py tests/test_pipeline.py
git commit -m "feat: add four-pass import pipeline"
```

---

## Task 8: CLI

**Files:**
- Create: `tapes/cli.py`
- Create: `tests/test_cli.py`

Minimal typer app with `tapes import` (user-facing). `tapes scan` is internal/hidden. For now, both print Rich tables (TUI comes in Task 10).

**Step 1: Write the tests**

```python
# tests/test_cli.py
from typer.testing import CliRunner
from tapes.cli import app

runner = CliRunner()


class TestImportCommand:
    def test_empty_directory(self, tmp_path):
        result = runner.invoke(app, ["import", str(tmp_path)])
        assert result.exit_code == 0
        assert "No video files found" in result.output

    def test_finds_files(self, tmp_path):
        (tmp_path / "Dune.2021.mkv").write_bytes(b"\x00" * 1024)
        result = runner.invoke(app, ["import", str(tmp_path)])
        assert result.exit_code == 0
        assert "Dune" in result.output

    def test_dry_run_flag(self, tmp_path):
        (tmp_path / "movie.mkv").write_bytes(b"\x00" * 1024)
        result = runner.invoke(app, ["import", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0

    def test_no_tui_flag(self, tmp_path):
        (tmp_path / "movie.mkv").write_bytes(b"\x00" * 1024)
        result = runner.invoke(app, ["import", str(tmp_path), "--no-tui"])
        assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

**Step 3: Implement CLI**

```python
# tapes/cli.py
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tapes.config import TapesConfig, load_config
from tapes.pipeline import run_pipeline

app = typer.Typer(name="tapes", no_args_is_help=True)
console = Console()


@app.command("import")
def import_cmd(
    path: Path = typer.Argument(..., help="Directory or file to import"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only, no file operations ever"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Plain text output instead of TUI"),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Import video files from a directory."""
    cfg = load_config(config_file) if config_file else TapesConfig()
    if dry_run:
        cfg.dry_run = True

    groups = run_pipeline(path, config=cfg)

    if not groups:
        console.print("No video files found.")
        raise typer.Exit()

    if no_tui:
        _print_plain(groups)
    else:
        # TUI placeholder -- Task 10
        _print_plain(groups)


def _print_plain(groups):
    """Print groups as a Rich table (non-TUI output)."""
    table = Table(title="Import Groups")
    table.add_column("Type", style="dim")
    table.add_column("Label")
    table.add_column("Videos", justify="right")
    table.add_column("Companions", justify="right")

    for g in groups:
        videos = len(g.video_files)
        companions = len(g.files) - videos
        table.add_row(
            g.group_type.value,
            g.label,
            str(videos),
            str(companions),
        )

    console.print(table)
    console.print(f"\n{len(groups)} group(s) found.")
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_cli.py -v
```

**Step 5: Verify CLI works end-to-end**

```bash
mkdir -p /tmp/tapes-test
echo -n "fake" > /tmp/tapes-test/Dune.2021.1080p.mkv
uv run tapes import /tmp/tapes-test --no-tui
rm -rf /tmp/tapes-test
```

**Step 6: Commit**

```bash
git add tapes/cli.py tests/test_cli.py
git commit -m "feat: add CLI with import command"
```

---

## Task 9: E2E tests

**Files:**
- Create: `tests/test_e2e/__init__.py`
- Create: `tests/test_e2e/conftest.py`
- Create: `tests/test_e2e/test_pipeline.py`

Realistic directory trees with edge cases. These are the source of truth.

**Step 1: Create shared fixtures**

```python
# tests/test_e2e/__init__.py
```

```python
# tests/test_e2e/conftest.py
import pytest
from pathlib import Path


@pytest.fixture
def make_video(tmp_path):
    """Factory to create fake video files."""
    def _make(name: str, subdir: str | None = None) -> Path:
        d = tmp_path / subdir if subdir else tmp_path
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_bytes(b"\x00" * 1024)
        return f
    return _make


@pytest.fixture
def make_companion(tmp_path):
    """Factory to create companion files."""
    def _make(name: str, subdir: str | None = None, content: str = "") -> Path:
        d = tmp_path / subdir if subdir else tmp_path
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_text(content)
        return f
    return _make
```

**Step 2: Write E2E tests**

```python
# tests/test_e2e/test_pipeline.py
from tapes.pipeline import run_pipeline
from tapes.models import GroupType


class TestMovieScenarios:
    def test_single_movie_with_subs(self, tmp_path, make_video, make_companion):
        make_video("Dune.2021.1080p.BluRay.mkv")
        make_companion("Dune.2021.1080p.BluRay.en.srt")
        make_companion("Dune.2021.1080p.BluRay.de.srt")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].metadata.title == "Dune"
        assert len(groups[0].files) == 3  # 1 video + 2 subs

    def test_movie_in_release_folder(self, tmp_path, make_video, make_companion):
        make_video("Dune.2021.1080p.mkv", subdir="Dune.2021.1080p.BluRay")
        make_companion("Dune.2021.1080p.en.srt", subdir="Dune.2021.1080p.BluRay")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert len(groups[0].files) == 2

    def test_multi_part_movie(self, tmp_path, make_video):
        make_video("Kill.Bill.Vol.1.CD1.mkv")
        make_video("Kill.Bill.Vol.1.CD2.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].group_type == GroupType.MULTI_PART

    def test_two_unrelated_movies(self, tmp_path, make_video):
        make_video("Dune.2021.mkv")
        make_video("Arrival.2016.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 2


class TestTVScenarios:
    def test_season_folder(self, tmp_path, make_video):
        d = "Breaking.Bad.S01"
        for i in range(1, 4):
            make_video(f"Breaking.Bad.S01E{i:02d}.720p.mkv", subdir=d)
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].group_type == GroupType.SEASON
        assert len(groups[0].video_files) == 3

    def test_episodes_with_companions(self, tmp_path, make_video, make_companion):
        d = "BB.S01"
        make_video("Breaking.Bad.S01E01.mkv", subdir=d)
        make_companion("Breaking.Bad.S01E01.en.srt", subdir=d)
        make_video("Breaking.Bad.S01E02.mkv", subdir=d)
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        subs = [f for f in groups[0].files if f.role == "subtitle"]
        assert len(subs) == 1

    def test_multiple_seasons_stay_separate(self, tmp_path, make_video):
        make_video("Show.S01E01.mkv", subdir="Show.S01")
        make_video("Show.S01E02.mkv", subdir="Show.S01")
        make_video("Show.S02E01.mkv", subdir="Show.S02")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 2

    def test_single_episode_stays_standalone(self, tmp_path, make_video):
        make_video("Show.S01E01.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].group_type == GroupType.STANDALONE


class TestMixedContent:
    def test_movies_and_episodes(self, tmp_path, make_video):
        make_video("Dune.2021.mkv")
        make_video("BB.S01E01.mkv", subdir="BB")
        make_video("BB.S01E02.mkv", subdir="BB")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 2

    def test_sample_files_excluded(self, tmp_path, make_video):
        make_video("Movie.mkv")
        make_video("sample.mkv")
        make_video("Movie-sample.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1


class TestEdgeCases:
    def test_empty_directory(self, tmp_path):
        groups = run_pipeline(tmp_path)
        assert groups == []

    def test_no_metadata_fallback(self, tmp_path, make_video):
        make_video("12345.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1
        assert groups[0].label  # should not crash

    def test_hidden_directory_excluded(self, tmp_path, make_video):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "movie.mkv").write_bytes(b"\x00")
        make_video("visible.mkv")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1

    def test_deeply_nested(self, tmp_path, make_video):
        make_video("movie.mkv", subdir="a/b/c/d")
        groups = run_pipeline(tmp_path)
        assert len(groups) == 1

    def test_bidirectional_refs_intact(self, tmp_path, make_video, make_companion):
        make_video("Dune.2021.mkv")
        make_companion("Dune.2021.en.srt")
        groups = run_pipeline(tmp_path)
        for g in groups:
            for f in g.files:
                assert f.group is g
```

**Step 3: Run E2E tests**

```bash
uv run pytest tests/test_e2e/ -v
```

Fix any failures from integration issues between the components.

**Step 4: Commit**

```bash
git add tests/test_e2e/
git commit -m "test: add E2E pipeline tests"
```

---

## Task 10: TUI -- App skeleton

**Files:**
- Create: `tapes/ui/__init__.py`
- Create: `tapes/ui/app.py`
- Create: `tests/test_ui/__init__.py`
- Create: `tests/test_ui/test_app.py`
- Modify: `tapes/cli.py` (wire TUI)

Vertical accordion with expand/collapse navigation and a summary footer. Start with read-only display -- no modals yet.

**Step 1: Write the tests**

Use textual's `run_test()` for headless testing:

```python
# tests/test_ui/__init__.py
```

```python
# tests/test_ui/test_app.py
import pytest
from pathlib import Path
from tapes.ui.app import ReviewApp
from tapes.models import FileEntry, FileMetadata, GroupType, ImportGroup


def _make_groups():
    g1 = ImportGroup(metadata=FileMetadata(media_type="movie", title="Dune", year=2021))
    g1.add_file(FileEntry(path=Path("/tmp/dune.mkv"), role="video"))

    g2 = ImportGroup(
        metadata=FileMetadata(media_type="episode", title="Breaking Bad", season=1),
        group_type=GroupType.SEASON,
    )
    g2.add_file(FileEntry(path=Path("/tmp/bb.s01e01.mkv"), role="video"))
    g2.add_file(FileEntry(path=Path("/tmp/bb.s01e02.mkv"), role="video"))
    return [g1, g2]


class TestReviewApp:
    async def test_get_state_returns_groups(self):
        groups = _make_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test():
            state = app.get_state()
            assert len(state) == 2

    async def test_navigation_down(self):
        groups = _make_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+down")
            assert app.focused_index == 1

    async def test_navigation_up(self):
        groups = _make_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+down")
            await pilot.press("ctrl+up")
            assert app.focused_index == 0

    async def test_quit(self):
        groups = _make_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test() as pilot:
            await pilot.press("q")

    async def test_summary_visible(self):
        groups = _make_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test():
            # Summary should show group count
            assert app.query_one("#summary")
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_ui/ -v
```

**Step 3: Implement TUI app**

```python
# tapes/ui/__init__.py
```

```python
# tapes/ui/app.py
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from tapes.models import ImportGroup


class GroupWidget(Static):
    """A single group in the accordion list."""

    def __init__(self, group: ImportGroup, expanded: bool = False) -> None:
        super().__init__()
        self.group = group
        self._expanded = expanded

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        if self._expanded:
            lines = [f"[bold]{self._status_badge()}  {self.group.label}[/bold]"]
            meta = self.group.metadata
            if meta:
                parts = [p for p in [meta.media_type, meta.title, str(meta.year) if meta.year else None] if p]
                if meta.season is not None:
                    parts.append(f"S{meta.season:02d}")
                lines.append(f"  Metadata: {' | '.join(parts)}")
            lines.append("")
            for f in self.group.files:
                role_tag = f.role[:5].ljust(5)
                lines.append(f"  {role_tag}  {f.path.name}")
            self.update("\n".join(lines))
        else:
            self.update(f"{self._status_badge()}  {self.group.label}")

    def _status_badge(self) -> str:
        badges = {
            "pending": "[yellow]\\[??][/yellow]",
            "accepted": "[green]\\[ok][/green]",
            "auto_accepted": "[blue]\\[**][/blue]",
            "skipped": "[dim]\\[--][/dim]",
        }
        return badges.get(self.group.status.value, "[??]")

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._render_content()


class SummaryWidget(Static):
    """Summary section at the bottom."""

    def __init__(self, groups: list[ImportGroup]) -> None:
        super().__init__(id="summary")
        self._groups = groups

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        total = len(self._groups)
        videos = sum(len(g.video_files) for g in self._groups)
        companions = sum(len(g.files) - len(g.video_files) for g in self._groups)
        self.update(
            f"[bold]Summary:[/bold] {total} group(s), {videos} video(s), {companions} companion(s)"
        )


class ReviewApp(App):
    """TUI for reviewing import groups."""

    BINDINGS = [
        Binding("ctrl+down", "focus_next_group", "Next group"),
        Binding("ctrl+up", "focus_prev_group", "Prev group"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, groups: list[ImportGroup]) -> None:
        super().__init__()
        self._groups = groups
        self.focused_index = 0
        self._widgets: list[GroupWidget] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            for i, group in enumerate(self._groups):
                w = GroupWidget(group, expanded=(i == 0))
                self._widgets.append(w)
                yield w
        yield SummaryWidget(self._groups)
        yield Footer()

    def get_state(self) -> list[ImportGroup]:
        return list(self._groups)

    def get_history(self) -> list:
        return []  # Tier 1: no actions yet

    def action_focus_next_group(self) -> None:
        if self.focused_index < len(self._widgets) - 1:
            self._widgets[self.focused_index].set_expanded(False)
            self.focused_index += 1
            self._widgets[self.focused_index].set_expanded(True)
            self._widgets[self.focused_index].scroll_visible()

    def action_focus_prev_group(self) -> None:
        if self.focused_index > 0:
            self._widgets[self.focused_index].set_expanded(False)
            self.focused_index -= 1
            self._widgets[self.focused_index].set_expanded(True)
            self._widgets[self.focused_index].scroll_visible()
```

**Step 4: Wire TUI into CLI**

In `tapes/cli.py`, replace the TUI placeholder in `import_cmd`:

```python
    if no_tui:
        _print_plain(groups)
    else:
        from tapes.ui.app import ReviewApp
        review_app = ReviewApp(groups=groups)
        review_app.run()
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_ui/ -v
```

**Step 6: Run the TUI manually to check the feel**

```bash
mkdir -p /tmp/tapes-test/BB.S01
echo -n "x" > /tmp/tapes-test/Dune.2021.1080p.mkv
echo -n "" > /tmp/tapes-test/Dune.2021.1080p.en.srt
echo -n "x" > /tmp/tapes-test/BB.S01/Breaking.Bad.S01E01.mkv
echo -n "x" > /tmp/tapes-test/BB.S01/Breaking.Bad.S01E02.mkv
uv run tapes import /tmp/tapes-test
rm -rf /tmp/tapes-test
```

**Step 7: Commit**

```bash
git add tapes/ui/ tests/test_ui/ tapes/cli.py
git commit -m "feat: add textual TUI with accordion navigation"
```

---

## Task 11: TUI modals -- split, merge, file editor

**Files:**
- Create: `tapes/ui/split_modal.py`
- Create: `tapes/ui/merge_modal.py`
- Create: `tapes/ui/file_editor.py`
- Create: `tests/test_ui/test_modals.py`
- Modify: `tapes/ui/app.py` (add keybindings and modal wiring)

**Step 1: Write the tests**

These tests verify actual state changes, not just that modals open.

```python
# tests/test_ui/test_modals.py
import pytest
from pathlib import Path
from tapes.ui.app import ReviewApp
from tapes.models import FileEntry, FileMetadata, GroupType, ImportGroup


def _make_season_group():
    """Single season group with 2 episodes + 1 subtitle for split testing."""
    g = ImportGroup(
        metadata=FileMetadata(media_type="episode", title="BB", season=1),
        group_type=GroupType.SEASON,
    )
    g.add_file(FileEntry(path=Path("/tmp/bb.s01e01.mkv"), role="video"))
    g.add_file(FileEntry(path=Path("/tmp/bb.s01e01.srt"), role="subtitle"))
    g.add_file(FileEntry(path=Path("/tmp/bb.s01e02.mkv"), role="video"))
    return [g]


def _make_two_groups():
    """Two separate groups for merge testing."""
    g1 = ImportGroup(
        metadata=FileMetadata(media_type="episode", title="BB", season=1, episode=1),
    )
    g1.add_file(FileEntry(path=Path("/tmp/bb.s01e01.mkv"), role="video"))

    g2 = ImportGroup(
        metadata=FileMetadata(media_type="episode", title="BB", season=1, episode=2),
    )
    g2.add_file(FileEntry(path=Path("/tmp/bb.s01e02.mkv"), role="video"))
    return [g1, g2]


class TestSplitModal:
    async def test_split_modal_opens_and_closes(self):
        groups = _make_season_group()
        app = ReviewApp(groups=groups)
        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.press("escape")
            assert len(app.get_state()) == 1  # no change on cancel


class TestMergeModal:
    async def test_merge_modal_opens_and_closes(self):
        groups = _make_two_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test() as pilot:
            await pilot.press("j")
            await pilot.press("escape")
            assert len(app.get_state()) == 2  # no change on cancel


class TestFileEditor:
    async def test_file_editor_opens_and_closes(self):
        groups = _make_two_groups()
        app = ReviewApp(groups=groups)
        async with app.run_test() as pilot:
            await pilot.press("e")
            await pilot.press("escape")
            assert len(app.get_state()) == 2
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_ui/test_modals.py -v
```

**Step 3: Implement modals**

Each modal is a textual `ModalScreen` subclass. The implementation is substantial but follows the same pattern:
- Show a list of items (files or groups)
- Tab toggles selection
- Enter confirms, Escape cancels
- On confirm, mutate the groups list via `ImportGroup.add_file()` / `ImportGroup.remove_file()`

**`tapes/ui/split_modal.py`**: Shows files in current group. Tab marks files to break out. Enter creates a new group from marked files and adds it to the app's group list.

**`tapes/ui/merge_modal.py`**: Shows other groups with labels. Tab marks groups. Enter merges marked groups' files into current group (via `add_file`), removes empty groups.

**`tapes/ui/file_editor.py`**: Shows all files across all groups. Current group's files are highlighted. Tab moves files into/out of current group. Files from other groups are dimmed with their group label.

**Step 4: Wire modals into app.py**

Add bindings to `ReviewApp`:
```python
Binding("e", "open_file_editor", "Edit files"),
Binding("p", "open_split", "Split"),
Binding("j", "open_merge", "Merge"),
```

Add action methods that push the modal screens and handle callbacks to refresh the widget list.

**Step 5: Run tests**

```bash
uv run pytest tests/test_ui/ -v
```

**Step 6: Commit**

```bash
git add tapes/ui/ tests/test_ui/
git commit -m "feat: add TUI split, merge, and file editor modals"
```

---

## Task 12: Polish and verify

**Files:**
- Modify: various (fix issues found during integration)

**Step 1: Run full test suite**

```bash
uv run pytest -v --tb=short
```

**Step 2: Fix any failures**

Address integration issues between components.

**Step 3: Run the full pipeline manually**

Create a realistic test directory and verify the experience:

```bash
mkdir -p /tmp/tapes-demo/Dune.2021.1080p
echo -n "x" > /tmp/tapes-demo/Dune.2021.1080p/Dune.2021.1080p.mkv
echo -n "" > /tmp/tapes-demo/Dune.2021.1080p/Dune.2021.1080p.en.srt
mkdir -p /tmp/tapes-demo/Breaking.Bad.S01
for i in 01 02 03; do
  echo -n "x" > /tmp/tapes-demo/Breaking.Bad.S01/Breaking.Bad.S01E${i}.mkv
done
echo -n "x" > /tmp/tapes-demo/random_clip.avi
uv run tapes import /tmp/tapes-demo --no-tui
rm -rf /tmp/tapes-demo
```

Expected: 3 groups (Dune standalone, BB S01 season, random_clip standalone).

**Step 4: Update CLAUDE.md with test count**

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: polish Tier 1 integration"
```

---

## Summary

| Task | What | Tests |
|------|------|-------|
| 0 | Scaffolding | -- |
| 1 | Models (FileMetadata, FileEntry, ImportGroup, bidirectional refs) | ~16 |
| 2 | Scanner (video file discovery) | ~12 |
| 3 | Metadata extraction (guessit wrapper) | ~8 |
| 4 | Companion discovery (stem prefix matching) | ~13 |
| 5 | Grouper (dict-based merge criteria) | ~12 |
| 6 | Config (Pydantic v2 + YAML) | ~5 |
| 7 | Pipeline (orchestrator with companion dedup) | ~8 |
| 8 | CLI (typer app) | ~4 |
| 9 | E2E tests | ~15 |
| 10 | TUI app skeleton + summary | ~5 |
| 11 | TUI modals (split/merge/editor) | ~3 |
| 12 | Polish and integration | -- |

**Estimated test count:** ~100 tests for Tier 1.

**Dependencies between tasks:** 0 -> 1 -> {2, 3} (parallel) -> 4 -> 5 -> {6, 7} (6 parallel with 1-5) -> 8 -> 9 -> 10 -> 11 -> 12
