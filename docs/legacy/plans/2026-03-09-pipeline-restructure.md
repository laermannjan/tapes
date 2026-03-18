# Pipeline Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure `tapes/pipeline.py` to match the authoritative mental model in `docs/pipeline-model.md`, fixing two structural bugs.

**Architecture:** Two targeted fixes to `_query_tmdb_for_node` and `_query_episodes`. No new functions, no API changes. The public interface stays identical.

**Tech Stack:** Python, pytest, unittest.mock.patch

---

## Bug Summary

**Reference:** `docs/pipeline-model.md` (Key Invariants section)

Two violations of the mental model exist in `tapes/pipeline.py`:

1. **Invariant #1 violated: show-level sources missing for auto-accepted TV shows.**
   In `_query_tmdb_for_node`, when `should_auto_accept` fires for a TV show,
   the code calls `_query_episodes` (which adds episode sources) and returns,
   but never adds the show-level `tmdb_sources` to `node.sources`. Movies and
   non-auto-accepted shows do add them. Location: lines 538-562.

2. **Invariant #3 violated: early stopping in episode query.**
   In `_query_episodes`, lines 659-661 break out of the season loop when any
   episode exceeds the threshold. The mental model says: "for EVERY season",
   "No early stopping. Score every episode across every season, keep top 3."

---

### Task 1: Show-level sources always added for auto-accepted TV shows

**Files:**
- Modify: `tests/test_ui/test_pipeline.py`
- Modify: `tapes/pipeline.py` (inside `_query_tmdb_for_node`, the auto-accept branch)

**Step 1: Write the failing test**

Add to `TestTwoStageFlow` in `tests/test_ui/test_pipeline.py`:

```python
def test_auto_accepted_tv_show_has_show_level_sources(self, mock_tmdb) -> None:
    """Auto-accepted TV show should have show-level TMDB sources on
    node.sources, not just episode sources.
    Invariant #1: sources are always added."""
    model = _make_model("Breaking.Bad.S01E01.mkv")
    run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
    node = model.all_files()[0]
    # Should have BOTH show-level and episode-level sources
    tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
    show_sources = [s for s in tmdb_sources if "episode_title" not in s.fields]
    episode_sources = [s for s in tmdb_sources if "episode_title" in s.fields]
    assert len(show_sources) >= 1, f"Expected show-level sources, got: {tmdb_sources}"
    assert len(episode_sources) >= 1, f"Expected episode sources, got: {tmdb_sources}"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestTwoStageFlow::test_auto_accepted_tv_show_has_show_level_sources -v`
Expected: FAIL -- `show_sources` is empty because show-level sources are not
added in the auto-accept TV path.

**Step 3: Fix the code**

In `tapes/pipeline.py`, in `_query_tmdb_for_node`, the auto-accept branch
currently has this structure (around line 538):

```python
        # Stage 2: if TV show, fetch episodes (which add their own sources)
        if best.fields.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(...)
            return

        # For movies: add sources so user can review alternatives in the detail view
        _sources_auto = list(tmdb_sources)
        def _extend_auto(...):
            _n.sources.extend(_s)
        _post(_extend_auto)
        return
```

Change to: move the source-adding code BEFORE the episode-vs-movie branch so
it always runs for both movies and TV shows:

```python
        # Always add show/movie-level sources (invariant #1)
        _sources_auto = list(tmdb_sources)

        def _extend_auto(_n: FileNode = node, _s: list[Source] = _sources_auto) -> None:
            _n.sources.extend(_s)

        _post(_extend_auto)

        # Stage 2: if TV show, fetch episodes (which add their own sources)
        if best.fields.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(
                node,
                token,
                threshold,
                best.fields,
                cache=cache,
                client=client,
                post_update=_post,
                max_results=max_results,
                max_retries=max_retries,
                language=language,
                can_stage=can_stage,
            )

        return
```

This eliminates the separate movie-only source-adding block. Both movies and
TV shows now add show-level sources before the branch.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestTwoStageFlow -v`
Expected: All pass including the new test.

**Step 5: Run full pipeline tests to check for regressions**

Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: All pass. The change only adds sources that were previously missing;
no existing assertion checks for their absence.

**Step 6: Commit**

```bash
git add tests/test_ui/test_pipeline.py tapes/pipeline.py
git commit -m "fix: always add show-level sources for auto-accepted TV shows

Invariant #1 from docs/pipeline-model.md: every TMDB query populates
node.sources, whether auto-accept fires or not. Previously, auto-accepted
TV shows skipped adding show-level sources (only episode sources were
added via _query_episodes). Now show-level sources are added before the
movie-vs-episode branch."
```

---

### Task 2: Remove early stopping in episode query

**Files:**
- Modify: `tests/test_ui/test_pipeline.py`
- Modify: `tapes/pipeline.py` (inside `_query_episodes`, the season loop)

**Important:** Do NOT modify the shared `_mock_get_season_episodes` function.
Changing it would break `TestEpisodeConfidenceGate.test_low_confidence_episode_not_applied`
which relies on season 3 returning no data. Use a local patch override in the
new test instead.

**Step 1: Write the failing test**

Add a new test class in `tests/test_ui/test_pipeline.py`:

```python
class TestEpisodeQueryAllSeasons:
    """Invariant #3: episode query fetches ALL seasons, no early stopping."""

    def test_queries_all_seasons(self, mock_tmdb) -> None:
        """Episode query must call get_season_episodes for every season,
        even when a confident match is found in the first season tried."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
            },
            sources=[],
        )
        # Override get_season_episodes to count calls per season
        with patch(
            "tapes.tmdb.get_season_episodes", side_effect=_mock_get_season_episodes
        ) as mock_eps:
            refresh_tmdb_source(node, token=TOKEN)
            # get_show returns seasons [1,2,3,4,5]. ALL must be queried.
            assert mock_eps.call_count == 5, (
                f"Expected 5 season queries (one per season), got {mock_eps.call_count}"
            )
```

The node has `tmdb_id` set, so `_query_tmdb_for_node` takes the tmdb_id
shortcut directly to `_query_episodes`. Season 1 is tried first
(`query_season=1`). S01E01 matches with confidence 0.9 (>= 0.85 threshold).
With early stopping, the loop breaks after season 1 (call_count=1).
Without early stopping, all 5 seasons are queried (call_count=5).

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestEpisodeQueryAllSeasons::test_queries_all_seasons -v`
Expected: FAIL -- `assert 1 == 5` (early stopping after season 1)

**Step 3: Fix the code**

In `tapes/pipeline.py`, in `_query_episodes`, remove the early stopping block.
Find and delete these lines:

```python
        # If we found a match in this season, stop searching more
        if any(s.confidence >= threshold for s in all_episode_sources):
            break
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestEpisodeQueryAllSeasons -v`
Expected: PASS

**Step 5: Run full pipeline tests to check for regressions**

Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: All pass. The mock returns `[]` for seasons 2-5 (except season 1),
so removing early stopping adds empty-list iterations that don't change
results for existing tests.

**Step 6: Commit**

```bash
git add tests/test_ui/test_pipeline.py tapes/pipeline.py
git commit -m "fix: episode query fetches all seasons without early stopping

Invariant #3 from docs/pipeline-model.md: score every episode across
every season, keep top 3. The early-stop optimization broke this by
stopping the season loop when any episode exceeded the threshold.
This prevented episodes in later seasons from being scored."
```

---

### Task 3: Full verification

**Step 1: Run the full test suite**

Run: `uv run pytest -x -q`
Expected: 697+ tests pass (695 existing + 2 new), 0 failures.

**Step 2: Run linters**

Run: `uv tool run ruff check tapes/pipeline.py tests/test_ui/test_pipeline.py`
Run: `uv tool run ruff format --check tapes/pipeline.py tests/test_ui/test_pipeline.py`
Run: `uv tool run ty check`
Expected: No errors.
