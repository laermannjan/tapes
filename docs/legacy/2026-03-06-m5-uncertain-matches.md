# M5: Uncertain Matches Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce per-episode grouping, visual clustering, match sub-rows with accept/reject, and a selection hierarchy for seasons/shows.

**Architecture:** Remove season-merge from the grouper so each group is one movie or one episode. `build_grid_rows` clusters sibling episode groups visually (no blank row between them). Query produces match sub-rows (`RowKind.MATCH` / `RowKind.NO_MATCH`) inserted after the first video of each group. Accept/reject on match rows updates the group and removes the sub-row.

**Tech Stack:** Python 3.11+, textual, rich, pytest

---

## Task 1: Remove `same_season` from default grouper criteria

The grouper currently merges episodes of the same show+season into one `SEASON` group. We want each episode to stay as its own group.

**Files:**
- Modify: `tapes/grouper.py`
- Modify: `tapes/models.py`
- Modify: `tests/test_grouper.py`
- Modify: `tests/test_e2e/test_pipeline.py`

**Step 1: Update `tapes/models.py` -- remove `GroupType.SEASON`**

```python
class GroupType(Enum):
    STANDALONE = "standalone"
    MULTI_PART = "multi_part"
```

**Step 2: Update `tapes/grouper.py` -- remove `same_season`, update default criteria**

Delete the `same_season` function entirely. Update `group_files` default:

```python
def group_files(
    groups: list[ImportGroup],
    criteria: list[MergeCriterion] | None = None,
) -> list[ImportGroup]:
    """Apply merge criteria sequentially (default: [same_multi_part])."""
    if criteria is None:
        criteria = [same_multi_part]
    for criterion in criteria:
        groups = criterion(groups)
    return groups
```

**Step 3: Update `tests/test_grouper.py`**

- Delete entire `TestSameSeason` class.
- In `TestGroupFiles`:
  - `test_full_pipeline_mixed_content`: episodes no longer merge. Expect 5 groups (ep1, ep2, s02e01, kill bill merged, inception).

Wait -- the test has S1E1, S1E2, S2E1 episodes plus Kill Bill (2 parts) plus Inception. Without season merge: S1E1, S1E2, S2E1 stay separate = 3 episode groups. Kill Bill merges = 1. Inception = 1. Total = 5.

```python
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
        # 3 episode groups (no season merge) + 1 Kill Bill merged + 1 Inception = 5
        assert len(result) == 5
        multi_part = [g for g in result if g.group_type == GroupType.MULTI_PART]
        assert len(multi_part) == 1
        assert len(multi_part[0].files) == 2
        standalone = [g for g in result if g.group_type == GroupType.STANDALONE]
        assert len(standalone) == 4

    def test_preserves_companions_through_merge(self):
        # Now tests multi-part merge instead of season merge
        g1 = _group("Kill Bill", "movie", part=1, files=[Path("kb1.mkv")])
        g1.add_file(FileEntry(path=Path("kb1.srt"), role="subtitle"))
        g2 = _group("Kill Bill", "movie", part=2, files=[Path("kb2.mkv")])
        g2.add_file(FileEntry(path=Path("kb2.nfo"), role="metadata"))
        result = same_multi_part([g1, g2])
        assert len(result) == 1
        merged = result[0]
        paths = {f.path for f in merged.files}
        assert Path("kb1.mkv") in paths
        assert Path("kb1.srt") in paths
        assert Path("kb2.mkv") in paths
        assert Path("kb2.nfo") in paths

    def test_files_point_to_merged_group(self):
        g1 = _group("Kill Bill", "movie", part=1, files=[Path("kb1.mkv")])
        g2 = _group("Kill Bill", "movie", part=2, files=[Path("kb2.mkv")])
        result = same_multi_part([g1, g2])
        merged = result[0]
        for f in merged.files:
            assert f.group is merged
```

**Step 4: Update `tests/test_e2e/test_pipeline.py`**

Tests that expect `GroupType.SEASON` or season merging need updating:

- `test_season_folder_three_episodes`: expect 3 groups (one per episode), each STANDALONE
- `test_episodes_with_per_episode_subtitles`: expect 2 groups, each STANDALONE with 1 video + 1 subtitle
- `test_multiple_seasons_stay_separate`: expect 4 groups (one per episode), all STANDALONE
- `test_single_episode_stays_standalone`: unchanged
- `test_movies_and_episodes_together`: expect 3 groups (1 movie + 2 episodes), all STANDALONE

```python
class TestTVScenarios:
    def test_season_folder_three_episodes(self, tmp_path, make_video):
        """Season folder with 3 episodes -> 3 STANDALONE groups, 1 video each."""
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
        """Episodes with per-episode subtitles -> 2 groups, each with video + subtitle."""
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
        """Episodes from different seasons -> 4 separate groups."""
        make_video("Show.S01E01.mkv", subdir="Show.S01")
        make_video("Show.S01E02.mkv", subdir="Show.S01")
        make_video("Show.S02E01.mkv", subdir="Show.S02")
        make_video("Show.S02E02.mkv", subdir="Show.S02")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 4
        for g in groups:
            assert g.group_type == GroupType.STANDALONE

    def test_single_episode_stays_standalone(self, tmp_path, make_video):
        """A single episode -> STANDALONE type."""
        make_video("Friends.S03E07.mkv")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 1
        g = groups[0]
        assert g.group_type == GroupType.STANDALONE
        assert g.metadata.media_type == "episode"
```

```python
class TestMixedScenarios:
    def test_movies_and_episodes_together(self, tmp_path, make_video):
        """A movie and two same-season episodes -> 3 groups, all standalone."""
        make_video("Inception.2010.mkv")
        make_video("Show.S01E01.mkv", subdir="Show.S01")
        make_video("Show.S01E02.mkv", subdir="Show.S01")

        groups = run_pipeline(tmp_path)

        assert len(groups) == 3
        assert all(g.group_type == GroupType.STANDALONE for g in groups)
```

**Step 5: Run all tests**

Run: `uv run pytest tests/test_grouper.py tests/test_e2e/test_pipeline.py -v`
Expected: all pass

**Step 6: Commit**

```
git add tapes/models.py tapes/grouper.py tests/test_grouper.py tests/test_e2e/test_pipeline.py
git commit -m "refactor: remove season merge, groups are per-episode"
```

---

## Task 2: Visual clustering in `build_grid_rows`

Sibling episode groups (same title+season) should not have blank separator rows between them. Only different movies, different shows, or different seasons get blank rows.

**Files:**
- Modify: `tapes/ui/models.py`
- Modify: `tests/test_ui/test_grid_models.py`

**Step 1: Write the tests**

Add to `tests/test_ui/test_grid_models.py`:

```python
def test_episode_groups_same_season_no_blank_between():
    """Sibling episodes (same title+season) cluster without blank rows."""
    ep1_meta = FileMetadata(media_type="episode", title="Breaking Bad", season=1, episode=1)
    ep1 = ImportGroup(metadata=ep1_meta)
    ep1.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep1_meta))

    ep2_meta = FileMetadata(media_type="episode", title="Breaking Bad", season=1, episode=2)
    ep2 = ImportGroup(metadata=ep2_meta)
    ep2.add_file(FileEntry(path=Path("BB.S01E02.mkv"), metadata=ep2_meta))

    rows = build_grid_rows([ep1, ep2])
    # No blank row between sibling episodes
    assert len(rows) == 2
    assert all(r.kind == RowKind.FILE for r in rows)


def test_different_seasons_get_blank_between():
    """Different seasons of same show get blank separator."""
    ep1_meta = FileMetadata(media_type="episode", title="BB", season=1, episode=1)
    ep1 = ImportGroup(metadata=ep1_meta)
    ep1.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep1_meta))

    ep2_meta = FileMetadata(media_type="episode", title="BB", season=2, episode=1)
    ep2 = ImportGroup(metadata=ep2_meta)
    ep2.add_file(FileEntry(path=Path("BB.S02E01.mkv"), metadata=ep2_meta))

    rows = build_grid_rows([ep1, ep2])
    assert len(rows) == 3
    assert rows[1].kind == RowKind.BLANK


def test_different_shows_get_blank_between():
    """Different shows get blank separator even with same season number."""
    ep1_meta = FileMetadata(media_type="episode", title="BB", season=1, episode=1)
    ep1 = ImportGroup(metadata=ep1_meta)
    ep1.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep1_meta))

    ep2_meta = FileMetadata(media_type="episode", title="Office", season=1, episode=1)
    ep2 = ImportGroup(metadata=ep2_meta)
    ep2.add_file(FileEntry(path=Path("Office.S01E01.mkv"), metadata=ep2_meta))

    rows = build_grid_rows([ep1, ep2])
    assert len(rows) == 3
    assert rows[1].kind == RowKind.BLANK


def test_movie_and_episode_get_blank_between():
    """Movie followed by episodes gets blank separator."""
    movie_meta = FileMetadata(media_type="movie", title="Dune", year=2021)
    movie = ImportGroup(metadata=movie_meta)
    movie.add_file(FileEntry(path=Path("Dune.mkv"), metadata=movie_meta))

    ep_meta = FileMetadata(media_type="episode", title="BB", season=1, episode=1)
    ep = ImportGroup(metadata=ep_meta)
    ep.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep_meta))

    rows = build_grid_rows([movie, ep])
    assert len(rows) == 3
    assert rows[1].kind == RowKind.BLANK
```

**Step 2: Run to verify failures**

Run: `uv run pytest tests/test_ui/test_grid_models.py -v`
Expected: `test_episode_groups_same_season_no_blank_between` fails (currently always inserts blank)

**Step 3: Implement**

Update `build_grid_rows` in `tapes/ui/models.py`:

```python
def _cluster_key(group: ImportGroup) -> tuple[str, int | None] | None:
    """Return a clustering key for sibling detection.

    Episode groups with the same (title_lower, season) are siblings and
    should not have blank rows between them. Returns None for non-episodes.
    """
    meta = group.metadata
    if meta.media_type == "episode" and meta.title and meta.season is not None:
        return (meta.title.lower(), meta.season)
    return None


def build_grid_rows(groups: list[ImportGroup]) -> list[GridRow]:
    """Convert ImportGroups into a flat list of GridRows.

    Blank separator rows are inserted between groups, except between
    sibling episode groups (same show + season).
    """
    rows: list[GridRow] = []
    prev_key: tuple[str, int | None] | None = None
    for i, group in enumerate(groups):
        cur_key = _cluster_key(group)
        if i > 0:
            # Insert blank unless both prev and current are siblings
            if prev_key is None or cur_key is None or prev_key != cur_key:
                rows.append(GridRow(kind=RowKind.BLANK))
        for entry in group.files:
            rows.append(GridRow(kind=RowKind.FILE, entry=entry, group=group))
        prev_key = cur_key
    return rows
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_grid_models.py -v`
Expected: all pass

**Step 5: Fix any broken grid tests**

The existing grid tests in `tests/test_ui/test_grid.py` use `_groups()` which has two movie groups (Dune, Arrival). These still get blank rows between them, so those tests should still pass. Run the full suite to verify:

Run: `uv run pytest tests/test_ui/ -v`

**Step 6: Commit**

```
git add tapes/ui/models.py tests/test_ui/test_grid_models.py
git commit -m "feat(ui): visual clustering for sibling episode groups"
```

---

## Task 3: Update mock data for per-episode groups

The CLI mock data currently creates one big `bb` group for all Breaking Bad episodes. Split it into per-episode groups.

**Files:**
- Modify: `tapes/cli.py`

**Step 1: Update `_mock_groups()`**

Replace the Breaking Bad block:

```python
    # -- Breaking Bad S01 (3 per-episode groups) --
    bb_episodes: list[ImportGroup] = []
    for ep in (1, 2, 3):
        ep_meta = FileMetadata(
            media_type="episode", title="Breaking Bad", season=1, episode=ep
        )
        ep_group = ImportGroup(metadata=ep_meta)
        ep_group.add_file(
            FileEntry(
                path=Path(f"Breaking.Bad.S01E{ep:02d}.720p.mkv"), metadata=ep_meta
            )
        )
        ep_group.add_file(FileEntry(path=Path(f"Breaking.Bad.S01E{ep:02d}.720p.en.srt")))
        bb_episodes.append(ep_group)
```

Update the return to unpack the episode groups:

```python
    return [dune, arrival, *bb_episodes, clip, bonus]
```

**Step 2: Test manually**

Run: `uv run tapes grid`
Expected: Breaking Bad episodes appear clustered (no blank rows between them) but as separate groups.

**Step 3: Commit**

```
git add tapes/cli.py
git commit -m "refactor(cli): mock data uses per-episode groups"
```

---

## Task 4: Extend mock TMDB to return confidence

**Files:**
- Modify: `tapes/ui/query.py`
- Create: `tests/test_ui/test_query.py`

**Step 1: Write the tests**

```python
"""Tests for mock TMDB query."""
from tapes.ui.query import mock_tmdb_lookup


def test_confident_match():
    result = mock_tmdb_lookup("Dune")
    assert result is not None
    fields, confidence = result
    assert fields["title"] == "Dune"
    assert confidence >= 0.9


def test_uncertain_match():
    result = mock_tmdb_lookup("Breaking Bad")
    assert result is not None
    fields, confidence = result
    assert fields["title"] == "Breaking Bad"
    assert confidence < 0.9


def test_no_match():
    result = mock_tmdb_lookup("nonexistent")
    assert result is None


def test_empty_title():
    result = mock_tmdb_lookup("")
    assert result is None
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_ui/test_query.py -v`
Expected: fails (current function returns dict, not tuple)

**Step 3: Implement**

Replace `tapes/ui/query.py`:

```python
"""Mock TMDB lookup for grid TUI."""
from __future__ import annotations

from typing import Any

# Mock database: title -> (fields, confidence).
# Confident matches (>= 0.9) auto-accept. Uncertain (< 0.9) become match sub-rows.
_MOCK_TMDB: dict[str, tuple[dict[str, Any], float]] = {
    "dune": ({"title": "Dune", "year": 2021}, 0.95),
    "arrival": ({"title": "Arrival", "year": 2016}, 0.95),
    "breaking bad": (
        {"title": "Breaking Bad", "year": 2008, "episode_title": "Pilot"},
        0.75,
    ),
    "interstellar": ({"title": "Interstellar", "year": 2014}, 0.95),
}

# Per-episode overrides for Breaking Bad (keyed by episode number).
_BB_EPISODES: dict[int, dict[str, Any]] = {
    1: {"episode_title": "Pilot"},
    2: {"episode_title": "Cat's in the Bag..."},
    3: {"episode_title": "...And the Bag's in the River"},
}

CONFIDENCE_THRESHOLD = 0.9


def mock_tmdb_lookup(
    title: str,
    *,
    episode: int | None = None,
) -> tuple[dict[str, Any], float] | None:
    """Look up a title in the mock TMDB database.

    Returns (fields_dict, confidence) if found, or None if no match.
    For episode lookups, merges episode-specific fields.
    """
    if not title:
        return None
    result = _MOCK_TMDB.get(title.lower())
    if result is None:
        return None
    fields, confidence = result
    fields = dict(fields)  # copy to avoid mutation
    # Merge episode-specific data
    if episode is not None and title.lower() == "breaking bad":
        ep_data = _BB_EPISODES.get(episode, {})
        fields.update(ep_data)
    return fields, confidence
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_query.py -v`
Expected: all pass

**Step 5: Commit**

```
git add tapes/ui/query.py tests/test_ui/test_query.py
git commit -m "feat(ui): mock TMDB returns confidence scores"
```

---

## Task 5: Add MATCH and NO_MATCH row kinds to models

**Files:**
- Modify: `tapes/ui/models.py`
- Modify: `tests/test_ui/test_grid_models.py`

**Step 1: Write the tests**

Add to `tests/test_ui/test_grid_models.py`:

```python
from tapes.ui.models import GridRow, RowKind, RowStatus, build_grid_rows


def test_match_row_holds_proposed_fields():
    match_row = GridRow(
        kind=RowKind.MATCH,
        group=ImportGroup(metadata=FileMetadata(title="Dune")),
        match_fields={"title": "Dune: Part One", "year": 2021},
        match_confidence=0.75,
    )
    assert match_row.match_fields["title"] == "Dune: Part One"
    assert match_row.match_confidence == 0.75


def test_no_match_row():
    no_match = GridRow(kind=RowKind.NO_MATCH, group=ImportGroup(metadata=FileMetadata()))
    assert no_match.kind == RowKind.NO_MATCH
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_ui/test_grid_models.py::test_match_row_holds_proposed_fields -v`
Expected: fails (MATCH exists but `match_fields` does not)

**Step 3: Implement**

Update `tapes/ui/models.py`:

In `RowKind`:
```python
class RowKind(Enum):
    FILE = auto()
    BLANK = auto()
    MATCH = auto()      # uncertain match sub-row (yellow label, cyan values)
    NO_MATCH = auto()   # no match sub-row (red label)
```

Add fields to `GridRow`:
```python
@dataclass
class GridRow:
    kind: RowKind
    entry: FileEntry | None = None
    group: ImportGroup | None = None
    status: RowStatus = RowStatus.RAW
    edited_fields: set[str] = field(default_factory=set)
    frozen_fields: set[str] = field(default_factory=set)
    _overrides: dict[str, Any] = field(default_factory=dict)
    # Match sub-row fields (only used when kind == MATCH)
    match_fields: dict[str, Any] = field(default_factory=dict)
    match_confidence: float = 0.0
    # Rows owned by this match sub-row (indices populated after build)
    owned_row_indices: list[int] = field(default_factory=list)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_grid_models.py -v`
Expected: all pass

**Step 5: Commit**

```
git add tapes/ui/models.py tests/test_ui/test_grid_models.py
git commit -m "feat(ui): add MATCH and NO_MATCH row kinds with fields"
```

---

## Task 6: Query logic produces match sub-rows

This is the core change. When `q` is pressed, the query now:
1. For confident matches (>= threshold): auto-accept as before (status `**`)
2. For uncertain matches (< threshold): insert a MATCH sub-row after the first video, set status to `??` on all group rows
3. For no match: insert a NO_MATCH sub-row after the first video

**Files:**
- Modify: `tapes/ui/grid.py`
- Modify: `tests/test_ui/test_grid.py`

**Step 1: Write the tests**

Add to `tests/test_ui/test_grid.py`:

```python
from tapes.ui.models import RowKind, RowStatus
from tapes.ui.query import CONFIDENCE_THRESHOLD


def _episode_groups():
    """Per-episode Breaking Bad groups (uncertain match in mock)."""
    groups = []
    for ep in (1, 2, 3):
        meta = FileMetadata(media_type="episode", title="Breaking Bad", season=1, episode=ep)
        g = ImportGroup(metadata=meta)
        g.add_file(FileEntry(path=Path(f"BB.S01E{ep:02d}.mkv"), metadata=meta))
        g.add_file(FileEntry(path=Path(f"BB.S01E{ep:02d}.en.srt")))
        groups.append(g)
    return groups


def _no_match_group():
    """A group with a title not in mock TMDB."""
    meta = FileMetadata(media_type="movie", title="Unknown Film")
    g = ImportGroup(metadata=meta)
    g.add_file(FileEntry(path=Path("unknown.mkv"), metadata=meta))
    return g


async def test_query_uncertain_creates_match_subrows():
    app = GridApp(_episode_groups())
    async with app.run_test() as pilot:
        # Query all
        await pilot.press("Q")
        # Should have MATCH sub-rows (uncertain confidence < 0.9)
        match_rows = [r for r in app._rows if r.kind == RowKind.MATCH]
        assert len(match_rows) == 3  # one per episode


async def test_query_uncertain_sets_status():
    app = GridApp(_episode_groups())
    async with app.run_test() as pilot:
        await pilot.press("Q")
        file_rows = [r for r in app._rows if r.kind == RowKind.FILE]
        for r in file_rows:
            assert r.status == RowStatus.UNCERTAIN


async def test_query_no_match_creates_no_match_subrow():
    app = GridApp([_no_match_group()])
    async with app.run_test() as pilot:
        await pilot.press("q")
        no_match_rows = [r for r in app._rows if r.kind == RowKind.NO_MATCH]
        assert len(no_match_rows) == 1


async def test_accept_match_updates_group():
    app = GridApp(_episode_groups())
    async with app.run_test() as pilot:
        await pilot.press("Q")
        # Navigate to first MATCH row
        match_idx = next(i for i, r in enumerate(app._rows) if r.kind == RowKind.MATCH)
        # Move cursor to that row
        while app.cursor_row != match_idx:
            await pilot.press("down")
        await pilot.press("enter")
        # Match row removed, owned file rows become AUTO
        assert all(r.kind != RowKind.MATCH for r in app._rows[:3])
        # First episode's file rows should be AUTO
        assert app._rows[0].status == RowStatus.AUTO


async def test_reject_match_reverts_group():
    app = GridApp(_episode_groups())
    async with app.run_test() as pilot:
        await pilot.press("Q")
        match_idx = next(i for i, r in enumerate(app._rows) if r.kind == RowKind.MATCH)
        while app.cursor_row != match_idx:
            await pilot.press("down")
        await pilot.press("backspace")
        # Match row removed, file rows revert to RAW
        assert all(r.kind != RowKind.MATCH for r in app._rows[:3])
        assert app._rows[0].status == RowStatus.RAW


async def test_cursor_skips_no_match_rows():
    app = GridApp([_no_match_group()])
    async with app.run_test() as pilot:
        await pilot.press("q")
        # Row 0 = file, row 1 = NO_MATCH
        assert app.cursor_row == 0
        await pilot.press("down")
        # Should not land on NO_MATCH row (stays at 0 since no more FILE rows)
        assert app._rows[app.cursor_row].kind != RowKind.NO_MATCH
```

**Step 2: Run to verify failures**

Run: `uv run pytest tests/test_ui/test_grid.py::test_query_uncertain_creates_match_subrows -v`
Expected: fails

**Step 3: Implement query logic in `tapes/ui/grid.py`**

Add import at top:
```python
from tapes.ui.query import mock_tmdb_lookup, CONFIDENCE_THRESHOLD
```

Replace `action_query` and `action_query_all` with a shared `_run_query` method:

```python
def _run_query(self, targets: list[int]) -> None:
    """Run query on target rows, producing match/no-match sub-rows."""
    if not self._grid:
        return

    self._undo = self._snapshot_for_query()

    # Collect unique groups from targets
    seen_groups: set[int] = set()
    groups_to_query: list[tuple[ImportGroup, list[int]]] = []
    for row_idx in targets:
        row = self._rows[row_idx]
        if row.kind != RowKind.FILE:
            continue
        group = row.group
        if group is None or id(group) in seen_groups:
            continue
        seen_groups.add(id(group))
        # Find all row indices belonging to this group
        group_row_indices = [
            i for i, r in enumerate(self._rows)
            if r.kind == RowKind.FILE and r.group is group
        ]
        groups_to_query.append((group, group_row_indices))

    # Process each group
    insertions: list[tuple[int, GridRow]] = []
    for group, group_row_indices in groups_to_query:
        meta = group.metadata
        episode = meta.episode if isinstance(meta.episode, int) else None
        result = mock_tmdb_lookup(meta.title or "", episode=episode)

        if result is None:
            # No match: insert NO_MATCH sub-row after first video
            first_video_idx = next(
                (i for i in group_row_indices if self._rows[i].is_video),
                group_row_indices[0]
            )
            no_match_row = GridRow(
                kind=RowKind.NO_MATCH,
                group=group,
                owned_row_indices=group_row_indices,
            )
            insertions.append((first_video_idx + 1, no_match_row))
        else:
            fields, confidence = result
            if confidence >= CONFIDENCE_THRESHOLD:
                # Confident: auto-accept
                for idx in group_row_indices:
                    self._rows[idx].apply_match(fields)
            else:
                # Uncertain: set status to ??, insert MATCH sub-row
                for idx in group_row_indices:
                    self._rows[idx].status = RowStatus.UNCERTAIN
                first_video_idx = next(
                    (i for i in group_row_indices if self._rows[i].is_video),
                    group_row_indices[0]
                )
                match_row = GridRow(
                    kind=RowKind.MATCH,
                    group=group,
                    match_fields=fields,
                    match_confidence=confidence,
                    owned_row_indices=group_row_indices,
                )
                insertions.append((first_video_idx + 1, match_row))

    # Insert sub-rows in reverse order to preserve indices
    for insert_idx, sub_row in sorted(insertions, key=lambda x: x[0], reverse=True):
        self._rows.insert(insert_idx, sub_row)

    # Recompute owned_row_indices after insertions shifted things
    self._reindex_owned_rows()

    self._jump_to_top_target(targets)
    self._grid.rows = self._rows
    self._grid.refresh_grid()

def _reindex_owned_rows(self) -> None:
    """Recompute owned_row_indices on MATCH/NO_MATCH rows after insertions."""
    for row in self._rows:
        if row.kind in (RowKind.MATCH, RowKind.NO_MATCH) and row.group is not None:
            row.owned_row_indices = [
                i for i, r in enumerate(self._rows)
                if r.kind == RowKind.FILE and r.group is row.group
            ]
```

Update `action_query` and `action_query_all`:

```python
def action_query(self) -> None:
    if not self._grid or self._editing:
        return
    self._run_query(self._target_rows())

def action_query_all(self) -> None:
    if not self._grid or self._editing:
        return
    self._run_query(self._file_rows())
```

Update `_file_rows` to also include MATCH rows as navigable:

```python
def _file_rows(self) -> list[int]:
    """Return indices of all navigable rows (FILE and MATCH, not NO_MATCH)."""
    return [i for i, r in enumerate(self._rows) if r.kind in (RowKind.FILE, RowKind.MATCH)]
```

Add accept and reject actions:

```python
BINDINGS = [
    # ... existing bindings ...
    Binding("enter", "accept_match", "Accept", show=False),
    Binding("backspace", "reject_match", "Reject", show=False),
]

def action_accept_match(self) -> None:
    """Accept the match sub-row at cursor."""
    if not self._grid or self._editing:
        return
    row = self._rows[self._grid._cursor_row]
    if row.kind != RowKind.MATCH:
        return

    self._undo = self._snapshot_for_query()

    # Apply match fields to all owned rows
    for idx in row.owned_row_indices:
        self._rows[idx].apply_match(row.match_fields)

    # Remove the match sub-row
    match_idx = self._grid._cursor_row
    self._rows.pop(match_idx)
    self._reindex_owned_rows()

    # Move cursor to the file row above (or stay)
    if match_idx > 0:
        self._grid._cursor_row = match_idx - 1
    self._grid.rows = self._rows
    self._grid.refresh_grid()

def action_reject_match(self) -> None:
    """Reject the match sub-row at cursor."""
    if not self._grid or self._editing:
        return
    row = self._rows[self._grid._cursor_row]
    if row.kind != RowKind.MATCH:
        return

    self._undo = self._snapshot_for_query()

    # Revert owned rows to RAW
    for idx in row.owned_row_indices:
        self._rows[idx].status = RowStatus.RAW

    # Remove the match sub-row
    match_idx = self._grid._cursor_row
    self._rows.pop(match_idx)
    self._reindex_owned_rows()

    if match_idx > 0:
        self._grid._cursor_row = match_idx - 1
    self._grid.rows = self._rows
    self._grid.refresh_grid()
```

For undo, we need a snapshot that captures the full row list (since sub-rows are inserted/removed). Add a new snapshot method:

```python
def _snapshot_for_query(self) -> list[tuple[int, dict[str, Any], RowStatus, set[str]]]:
    """Snapshot all rows for query undo. Stores the entire row list."""
    # Store as special marker + full rows copy
    return [
        (idx, dict(row._overrides), row.status, set(row.edited_fields))
        for idx, row in enumerate(self._rows)
        if row.kind == RowKind.FILE
    ]
```

Actually, query undo is more complex because we insert/remove rows. We need a different undo approach. Store the full `_rows` list:

Add a new field `_undo_rows: list[GridRow] | None = None` and capture/restore the full list:

```python
def __init__(self, groups, **kwargs):
    # ... existing ...
    self._undo_rows: list[GridRow] | None = None  # full row list snapshot for query undo

def _snapshot_for_query(self) -> None:
    """Snapshot the entire row list for undo."""
    import copy
    self._undo_rows = copy.deepcopy(self._rows)

def action_undo(self) -> None:
    """Undo the last edit or query."""
    if not self._grid or self._editing:
        return
    if self._undo_rows is not None:
        self._rows = self._undo_rows
        self._undo_rows = None
        self._grid.rows = self._rows
        self._grid.refresh_grid()
        return
    if self._undo is not None:
        for row_idx, old_overrides, old_status, old_edited in self._undo:
            row = self._rows[row_idx]
            row._overrides = old_overrides
            row.status = old_status
            row.edited_fields = old_edited
        self._undo = None
        self._grid.refresh_grid()
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_grid.py -v`
Expected: all pass (both old and new tests)

**Step 5: Commit**

```
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): query produces match/no-match sub-rows with accept/reject"
```

---

## Task 7: Render match and no-match sub-rows

**Files:**
- Modify: `tapes/ui/render.py`
- Modify: `tests/test_ui/test_render.py`

**Step 1: Write the tests**

Add to `tests/test_ui/test_render.py`:

```python
from tapes.ui.models import GridRow, RowKind, RowStatus


def test_render_match_subrow():
    match_row = GridRow(
        kind=RowKind.MATCH,
        group=ImportGroup(metadata=FileMetadata(title="Breaking Bad")),
        match_fields={"title": "Breaking Bad", "year": 2008, "episode_title": "Pilot"},
    )
    text = render_row(match_row, cursor_col=0, is_cursor_row=False)
    plain = text.plain
    assert "(match)" in plain
    assert "Breaking Bad" in plain
    assert "2008" in plain
    assert "Pilot" in plain


def test_render_no_match_subrow():
    no_match_row = GridRow(
        kind=RowKind.NO_MATCH,
        group=ImportGroup(metadata=FileMetadata()),
    )
    text = render_row(no_match_row, cursor_col=0, is_cursor_row=False)
    plain = text.plain
    assert "(no match)" in plain
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_ui/test_render.py::test_render_match_subrow -v`
Expected: fails (render_row doesn't handle MATCH kind)

**Step 3: Implement**

Add to `render_row` in `tapes/ui/render.py`, after the BLANK handler:

```python
    if row.kind == RowKind.MATCH:
        # Status: down-arrow indicator
        _col(t, " \u23bf  ", COL_WIDTHS["status"], "#333333")
        # Filepath: "(match)" in yellow
        _col(t, "(match)", COL_WIDTHS["filepath"], "#ccaa33")
        # Metadata columns: proposed values in cyan
        fields = row.match_fields
        match_values = [
            str(fields.get("title", "")),
            str(fields.get("year", "")),
            str(fields.get("season", "")),
            str(fields.get("episode", "")),
            str(fields.get("episode_title", "")),
        ]
        for i, (col_name, value) in enumerate(zip(FIELD_COLS, match_values)):
            bg = None
            if is_cursor_row and i == cursor_col:
                bg = BG_CELL_CUR
            elif i == cursor_col:
                bg = BG_COL_HI
            style = "#66bbcc" if value else "#333333"
            _col(t, value, COL_WIDTHS[col_name], style, bg=bg)
        return t

    if row.kind == RowKind.NO_MATCH:
        _col(t, " \u23bf  ", COL_WIDTHS["status"], "#333333")
        _col(t, "(no match)", COL_WIDTHS["filepath"], "#cc5555")
        for col_name in FIELD_COLS:
            _col(t, "", COL_WIDTHS[col_name], "#333333")
        return t
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_render.py -v`
Expected: all pass

**Step 5: Commit**

```
git add tapes/ui/render.py tests/test_ui/test_render.py
git commit -m "feat(ui): render match and no-match sub-rows"
```

---

## Task 8: Update footer with status counts after query

**Files:**
- Modify: `tapes/ui/grid.py`

**Step 1: Update `GridFooter.render` to show status counts**

When there are any non-RAW statuses, show counts like: `** 5  ?? 3  no match 2`

```python
def render(self) -> Text:
    t = Text()
    t.append(" ")

    if self._n_selected > 0:
        # ... selection footer unchanged ...
    else:
        # Count statuses
        file_rows = [r for r in self._rows if r.kind == RowKind.FILE]
        n_auto = sum(1 for r in file_rows if r.status == RowStatus.AUTO)
        n_uncertain = sum(1 for r in file_rows if r.status == RowStatus.UNCERTAIN)
        n_edited = sum(1 for r in file_rows if r.status == RowStatus.EDITED)
        n_no_match = sum(1 for r in self._rows if r.kind == RowKind.NO_MATCH)

        has_query_results = n_auto > 0 or n_uncertain > 0 or n_no_match > 0

        if has_query_results:
            # Post-query footer with status counts
            if n_auto:
                t.append("**", style="#55aa99")
                t.append(f" {n_auto}  ", style="#555555")
            if n_uncertain:
                t.append("??", style="#ccaa33")
                t.append(f" {n_uncertain}  ", style="#555555")
            if n_edited:
                t.append("!!", style="#a78bfa")
                t.append(f" {n_edited}  ", style="#555555")
            if n_no_match:
                t.append("no match", style="#cc5555")
                t.append(f" {n_no_match}  ", style="#555555")

            t.append("    ")
            hints = [
                ("enter", "accept"),
                ("bksp", "reject"),
                ("q", "re-query"),
                ("e", "edit"),
                ("p", "process"),
            ]
        else:
            # Normal mode footer (unchanged)
            n_files = len(file_rows)
            n_videos = sum(1 for r in file_rows if r.is_video)
            n_companions = sum(1 for r in file_rows if r.is_companion)
            n_groups = sum(1 for r in self._rows if r.kind == RowKind.BLANK) + 1

            for count, label in [
                (n_files, "files"),
                (n_groups, "groups"),
                (n_videos, "videos"),
                (n_companions, "companions"),
            ]:
                t.append(str(count), style="#dddddd")
                t.append(f" {label}  ", style="#555555")

            t.append("    ")
            hints = [
                ("e", "edit"),
                ("v", "select"),
                ("q", "query"),
                ("f", "freeze"),
                ("r", "reorg"),
                ("p", "process"),
                ("E", "all fields"),
            ]

        for key, desc in hints:
            t.append(key, style="#777777 underline")
            t.append(f" {desc}  ", style="#444444")

    return t
```

Also, after query/accept/reject, refresh footer:

In `_run_query`, `action_accept_match`, `action_reject_match`, add `self._refresh_footer()` at the end.

**Step 2: Test manually**

Run: `uv run tapes grid` then press `Q`.
Expected: footer shows status counts.

**Step 3: Commit**

```
git add tapes/ui/grid.py
git commit -m "feat(ui): footer shows status counts after query"
```

---

## Task 9: Selection hierarchy (shift-alt-V for season, shift-ctrl-V for show)

**Files:**
- Modify: `tapes/ui/grid.py`
- Modify: `tests/test_ui/test_grid.py`

**Step 1: Write the tests**

Add to `tests/test_ui/test_grid.py`:

```python
def _show_groups():
    """Two seasons of the same show, plus a movie."""
    groups = []
    for season in (1, 2):
        for ep in (1, 2):
            meta = FileMetadata(
                media_type="episode", title="Breaking Bad", season=season, episode=ep
            )
            g = ImportGroup(metadata=meta)
            g.add_file(FileEntry(path=Path(f"BB.S{season:02d}E{ep:02d}.mkv"), metadata=meta))
            groups.append(g)

    movie_meta = FileMetadata(media_type="movie", title="El Camino", year=2019)
    movie = ImportGroup(metadata=movie_meta)
    movie.add_file(FileEntry(path=Path("El.Camino.mkv"), metadata=movie_meta))
    groups.append(movie)
    return groups


async def test_select_season():
    """shift-alt-V selects all episodes of the same season."""
    app = GridApp(_show_groups())
    async with app.run_test() as pilot:
        # Cursor on S01E01 (row 0). Rows: S01E01=0, S01E02=1, BLANK=2, S02E01=3, S02E02=4, BLANK=5, ElCamino=6
        await pilot.press("ctrl+alt+shift+v")  # select season
        # Should select S01E01 and S01E02
        selected_rows = app._grid._selected_rows
        assert 0 in selected_rows
        assert 1 in selected_rows
        assert len(selected_rows) == 2


async def test_select_show():
    """shift-ctrl-V selects all episodes of the same show."""
    app = GridApp(_show_groups())
    async with app.run_test() as pilot:
        await pilot.press("ctrl+shift+v")  # select show
        # Should select all 4 BB episodes
        selected_rows = app._grid._selected_rows
        assert len(selected_rows) == 4
```

Note: Key bindings for shift-alt-V and shift-ctrl-V may vary by terminal. We'll use the Textual binding names. Check what Textual maps these to -- might be different key names. If needed, use simple alternatives.

Actually, terminal key combos with alt/ctrl+shift are unreliable. Let's use simpler bindings that work everywhere:

- `V` (shift-v): select group (existing, works)
- `ctrl+v`: select season
- `alt+v` or a different key entirely

Let me reconsider. Textual may not reliably capture ctrl+shift+v or alt+shift+v across terminals. Simpler approach:

- `V` (shift-v): select group (existing)
- `S` (shift-s): select season (all episodes same title+season)
- `A` (shift-a): select show/all (all episodes same title)

```python
async def test_shift_s_selects_season():
    """S selects all episodes of the same season."""
    app = GridApp(_show_groups())
    async with app.run_test() as pilot:
        # rows: 0=S01E01 1=S01E02 [blank] 2(actually 3)=S02E01 3(4)=S02E02 [blank] 4(6)=ElCamino
        await pilot.press("S")
        selected_rows = app._grid._selected_rows
        # S01E01 and S01E02
        assert 0 in selected_rows
        assert 1 in selected_rows
        assert len(selected_rows) == 2


async def test_shift_a_selects_show():
    """A selects all episodes of the same show."""
    app = GridApp(_show_groups())
    async with app.run_test() as pilot:
        await pilot.press("A")
        selected_rows = app._grid._selected_rows
        # All 4 BB episodes (rows 0, 1, 3, 4)
        assert len(selected_rows) == 4


async def test_shift_s_on_movie_same_as_shift_v():
    """S on a movie group acts the same as V (selects the group)."""
    app = GridApp(_show_groups())
    async with app.run_test() as pilot:
        # Navigate to El Camino
        # rows: 0=S01E01 1=S01E02 2=BLANK 3=S02E01 4=S02E02 5=BLANK 6=ElCamino
        for _ in range(6):
            await pilot.press("down")
        await pilot.press("S")
        selected_rows = app._grid._selected_rows
        assert len(selected_rows) == 1
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_ui/test_grid.py::test_shift_s_selects_season -v`
Expected: fails (no such binding)

**Step 3: Implement**

Add to `BINDINGS` in `GridApp`:

```python
Binding("S", "select_season", "Select season", show=False, key_display="shift+s"),
Binding("A", "select_show", "Select show", show=False, key_display="shift+a"),
```

Implement:

```python
def action_select_season(self) -> None:
    """Select all file rows of the same show+season as cursor row."""
    if not self._grid or self._editing:
        return
    cursor_row = self._rows[self._grid._cursor_row]
    if cursor_row.kind != RowKind.FILE or cursor_row.group is None:
        return

    meta = cursor_row.group.metadata
    col = self._grid._cursor_col

    # For non-episodes, fall back to group selection
    if meta.media_type != "episode" or meta.title is None or meta.season is None:
        self.action_select_group()
        return

    if self._grid._sel_col is None:
        self._grid._sel_col = col
    elif self._grid._sel_col != col:
        return

    title_lower = meta.title.lower()
    season = meta.season

    season_rows = {
        i for i, r in enumerate(self._rows)
        if r.kind == RowKind.FILE
        and r.group is not None
        and r.group.metadata.media_type == "episode"
        and r.group.metadata.title is not None
        and r.group.metadata.title.lower() == title_lower
        and r.group.metadata.season == season
    }

    if season_rows <= self._grid._selected_rows:
        self._grid._selected_rows -= season_rows
        if not self._grid._selected_rows:
            self._grid._sel_col = None
    else:
        self._grid._selected_rows |= season_rows

    self._grid.refresh_grid()
    self._refresh_footer()


def action_select_show(self) -> None:
    """Select all file rows of the same show as cursor row."""
    if not self._grid or self._editing:
        return
    cursor_row = self._rows[self._grid._cursor_row]
    if cursor_row.kind != RowKind.FILE or cursor_row.group is None:
        return

    meta = cursor_row.group.metadata
    col = self._grid._cursor_col

    if meta.media_type != "episode" or meta.title is None:
        self.action_select_group()
        return

    if self._grid._sel_col is None:
        self._grid._sel_col = col
    elif self._grid._sel_col != col:
        return

    title_lower = meta.title.lower()

    show_rows = {
        i for i, r in enumerate(self._rows)
        if r.kind == RowKind.FILE
        and r.group is not None
        and r.group.metadata.media_type == "episode"
        and r.group.metadata.title is not None
        and r.group.metadata.title.lower() == title_lower
    }

    if show_rows <= self._grid._selected_rows:
        self._grid._selected_rows -= show_rows
        if not self._grid._selected_rows:
            self._grid._sel_col = None
    else:
        self._grid._selected_rows |= show_rows

    self._grid.refresh_grid()
    self._refresh_footer()
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_grid.py -v`
Expected: all pass

**Step 5: Commit**

```
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): shift-S select season, shift-A select show"
```

---

## Task 10: Update design doc milestones

**Files:**
- Modify: `docs/plans/2026-03-06-grid-tui.md`

Mark M5 as done and update the M2-M4 notes with the grouper change. Also update the footer section.

**Step 1: Update the M5 section in the grid TUI doc**

Replace the M5 outline with a summary of what was implemented.

**Step 2: Commit**

```
git add docs/plans/2026-03-06-grid-tui.md
git commit -m "docs: update grid TUI plan with M5 implementation notes"
```

---

## Summary of changes

| Task | What | Files |
|------|------|-------|
| 1 | Remove season merge, groups are per-episode | grouper, models, tests |
| 2 | Visual clustering (no blank between siblings) | ui/models, tests |
| 3 | Update mock data for per-episode groups | cli |
| 4 | Mock TMDB returns confidence | query, tests |
| 5 | MATCH/NO_MATCH row kinds | ui/models, tests |
| 6 | Query produces sub-rows + accept/reject | ui/grid, tests |
| 7 | Render match/no-match sub-rows | ui/render, tests |
| 8 | Footer shows status counts | ui/grid |
| 9 | Selection hierarchy (S=season, A=show) | ui/grid, tests |
| 10 | Update design doc | docs |
