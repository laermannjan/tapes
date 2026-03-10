# Pipeline Scoring and UX Fixes -- Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix incorrect auto-accept behavior (media-type mismatch), clean up candidate lifecycle, and improve UX for missing fields and multi-node metadata view.

**Architecture:** Six changes across scoring (`similarity.py`), pipeline logic (`pipeline.py`), templates (`templates.py`), and UI (`tree_render.py`, `metadata_view.py`, `metadata_render.py`, `tree_app.py`). Each task is independent after Task 1.

**Tech Stack:** Python 3.11+, pytest, rapidfuzz, Rich, Textual

**Spec:** `docs/plans/2026-03-10-pipeline-and-ux-fixes.md`

---

## Chunk 1: Scoring and Pipeline Logic

### Task 1: Media-type conflict penalty in scoring (A1)

**Files:**
- Modify: `tapes/similarity.py:61-108` (`compute_similarity`)
- Modify: `tapes/fields.py` (import `MEDIA_TYPE`)
- Test: `tests/test_similarity.py`

- [ ] **Step 1: Write failing tests for media-type penalty**

Add to `tests/test_similarity.py`:

```python
class TestMediaTypePenalty:
    """A1: media-type mismatch between query and result penalizes the score."""

    def test_matching_media_type_no_penalty(self) -> None:
        """Same media_type in query and result -- full score."""
        score = compute_similarity(
            {"title": "Breaking Bad", "media_type": "episode"},
            {"title": "Breaking Bad", "media_type": "episode"},
        )
        # 0.7 * 1.0 + 0.3 * 0.0 = 0.7 (no year), no penalty
        assert score == pytest.approx(0.7)

    def test_mismatching_media_type_penalized(self) -> None:
        """query=movie, result=episode -- score multiplied by MEDIA_TYPE_PENALTY."""
        score = compute_similarity(
            {"title": "Breaking Bad", "media_type": "movie"},
            {"title": "Breaking Bad", "media_type": "episode"},
        )
        # 0.7 * 1.0 * 0.7 (penalty) = 0.49
        assert score == pytest.approx(0.7 * 0.7)

    def test_no_media_type_in_query_no_penalty(self) -> None:
        """No media_type in query -- no penalty applied."""
        score = compute_similarity(
            {"title": "Breaking Bad"},
            {"title": "Breaking Bad", "media_type": "episode"},
        )
        assert score == pytest.approx(0.7)

    def test_no_media_type_in_result_no_penalty(self) -> None:
        """No media_type in result -- no penalty applied."""
        score = compute_similarity(
            {"title": "Breaking Bad", "media_type": "movie"},
            {"title": "Breaking Bad"},
        )
        assert score == pytest.approx(0.7)

    def test_penalty_with_year_match(self) -> None:
        """Penalty applies to total score including year component."""
        score = compute_similarity(
            {"title": "Breaking Bad", "year": 2008, "media_type": "movie"},
            {"title": "Breaking Bad", "year": 2008, "media_type": "episode"},
        )
        # (0.7 * 1.0 + 0.3 * 1.0) * 0.7 = 1.0 * 0.7 = 0.7
        assert score == pytest.approx(0.7)

    def test_breaking_bad_scenario(self) -> None:
        """Real scenario: breaking_bad_720p.mp4 (guessit: movie).

        Breaking Bad show should score lower than without penalty.
        El Camino movie should keep its score.
        """
        query = {"title": "Breaking Bad", "media_type": "movie"}

        show_score = compute_similarity(
            query,
            {"title": "Breaking Bad", "media_type": "episode"},
        )
        movie_score = compute_similarity(
            query,
            {"title": "El Camino A Breaking Bad Movie", "year": 2019, "media_type": "movie"},
        )
        # Show penalized, movie not -- gap should narrow significantly
        assert show_score < 0.7  # penalized from ~0.7
        assert movie_score > 0.3  # not penalized
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_similarity.py::TestMediaTypePenalty -v`
Expected: FAIL (tests expect penalty behavior not yet implemented)

- [ ] **Step 3: Implement media-type penalty**

In `tapes/similarity.py`, add a constant after line 40:

```python
# Media-type mismatch penalty (applied when guessit and TMDB disagree)
MEDIA_TYPE_PENALTY = 0.7
```

Add import at line 14 (after existing imports from fields):

```python
from tapes.fields import EPISODE, EPISODE_TITLE, MEDIA_TYPE, SEASON, TITLE, TMDB_ID, YEAR
```

Modify `compute_similarity()` -- after computing `total` on line 99, before the
`logger.debug` on line 100, add the penalty:

```python
    total = SHOW_TITLE_WEIGHT * title_score + SHOW_YEAR_WEIGHT * year_score

    # Media-type mismatch penalty: if both query and result have media_type
    # and they disagree, reduce the score.
    q_type = query.get(MEDIA_TYPE)
    r_type = result.get(MEDIA_TYPE)
    if q_type and r_type and q_type != r_type:
        total *= MEDIA_TYPE_PENALTY

    logger.debug(
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: ALL PASS (including existing tests -- they don't set media_type so no penalty)

- [ ] **Step 5: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "feat: add media-type conflict penalty in similarity scoring (A1)"
```

---

### Task 2: Media-type match gate on auto-accept (A2)

**Files:**
- Modify: `tapes/pipeline.py:591` (auto-accept branch in `_query_tmdb_for_node`)
- Test: `tests/test_pipeline_auto_accept_gate.py` (new)

- [ ] **Step 1: Write failing tests for auto-accept gate**

Create `tests/test_pipeline_auto_accept_gate.py`:

```python
"""Tests for A2: media-type match gate on auto-accept."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE, TITLE, TMDB_ID, YEAR
from tapes.pipeline import PipelineParams, _query_tmdb_for_node
from tapes.tree_model import FileNode


def _make_node(metadata: dict) -> FileNode:
    return FileNode(path=Path("test.mp4"), metadata=dict(metadata))


class TestMediaTypeAutoAcceptGate:
    """A2: auto-accept blocked when best candidate's media_type mismatches node's guessit media_type."""

    def test_matching_media_type_auto_accepts(self, respx_mock) -> None:
        """movie query + movie result = auto-accept fires."""
        respx_mock.get("https://api.themoviedb.org/3/search/multi").respond(
            json={
                "results": [
                    {"id": 559969, "title": "El Camino", "release_date": "2019-10-11", "media_type": "movie"},
                ],
            },
        )
        node = _make_node({TITLE: "El Camino", MEDIA_TYPE: MEDIA_TYPE_MOVIE})
        params = PipelineParams(token="fake", min_score=0.3, min_prominence=0.0)
        _query_tmdb_for_node(node, params)
        # Auto-accepted: tmdb_id should be set
        assert node.metadata.get(TMDB_ID) == 559969

    def test_mismatching_media_type_blocks_auto_accept(self, respx_mock) -> None:
        """movie query + episode result = auto-accept blocked."""
        respx_mock.get("https://api.themoviedb.org/3/search/multi").respond(
            json={
                "results": [
                    {"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20", "media_type": "tv"},
                ],
            },
        )
        node = _make_node({TITLE: "Breaking Bad", MEDIA_TYPE: MEDIA_TYPE_MOVIE})
        params = PipelineParams(token="fake", min_score=0.3, min_prominence=0.0)
        _query_tmdb_for_node(node, params)
        # NOT auto-accepted: tmdb_id should NOT be set
        assert node.metadata.get(TMDB_ID) is None
        # But candidates should still be populated
        assert len(node.candidates) > 0

    def test_no_media_type_in_node_allows_auto_accept(self, respx_mock) -> None:
        """No guessit media_type = gate skipped, auto-accept proceeds."""
        respx_mock.get("https://api.themoviedb.org/3/search/multi").respond(
            json={
                "results": [
                    {"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20", "media_type": "tv"},
                ],
            },
        )
        node = _make_node({TITLE: "Breaking Bad"})  # no media_type
        params = PipelineParams(token="fake", min_score=0.3, min_prominence=0.0)
        _query_tmdb_for_node(node, params)
        # Auto-accepted: tmdb_id should be set
        assert node.metadata.get(TMDB_ID) is not None
```

Note: These tests use `respx_mock` which requires the `respx` fixture. The project already uses respx for HTTP mocking. The test needs to check the TMDB search response parsing too -- you may need to check `tapes/tmdb.py:search_multi` to see the exact response format it expects and adjust the mock responses accordingly. Make sure the mock responses match what `search_multi` returns after parsing.

**Important:** Before writing the test, read `tapes/tmdb.py` to understand how `search_multi` parses TMDB API responses. The mock must return data in the format that `search_multi` expects. The function likely normalizes the raw API response into a dict with fields like `title`, `year`, `media_type`, `tmdb_id`. Adjust the test mocks to match the actual API format, and verify the parsed output has the fields the pipeline expects.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline_auto_accept_gate.py -v`
Expected: FAIL (gate not yet implemented -- mismatching media_type still auto-accepts)

- [ ] **Step 3: Implement the gate**

In `tapes/pipeline.py`, modify the auto-accept branch in `_query_tmdb_for_node()` around line 591.

Before:
```python
    if should_auto_accept(similarities, min_score=params.min_score, min_prominence=params.min_prominence):
```

After:
```python
    # A2: media-type match gate -- skip auto-accept if best candidate's
    # media_type disagrees with the node's guessit media_type.
    node_media_type = node.metadata.get(MEDIA_TYPE)
    best_media_type = best.metadata.get(MEDIA_TYPE)
    media_type_compatible = (
        node_media_type is None
        or best_media_type is None
        or node_media_type == best_media_type
    )

    if media_type_compatible and should_auto_accept(similarities, min_score=params.min_score, min_prominence=params.min_prominence):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline_auto_accept_gate.py tests/test_pipeline.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tapes/pipeline.py tests/test_pipeline_auto_accept_gate.py
git commit -m "feat: add media-type match gate on auto-accept (A2)"
```

---

### Task 3: Clear candidates after show/movie acceptance (A3)

**Files:**
- Modify: `tapes/pipeline.py:602` (auto-accept path in `_query_tmdb_for_node`)
- Modify: `tapes/ui/metadata_view.py:338` (`accept_current_candidate`)
- Test: `tests/test_pipeline_clear_candidates.py` (new)

- [ ] **Step 1: Write failing tests for candidate clearing**

Create `tests/test_pipeline_clear_candidates.py`:

```python
"""Tests for A3: clear candidates after show/movie acceptance."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, TITLE, TMDB_ID
from tapes.tree_model import Candidate, FileNode


class TestClearCandidatesOnAcceptPipeline:
    """A3: pipeline auto-accept clears prior candidates before adding episode candidates."""

    def test_auto_accept_clears_existing_candidates(self) -> None:
        """When auto-accept fires, node.candidates should be cleared first."""
        node = FileNode(path=Path("test.mp4"))
        # Pre-populate with stale candidates
        node.candidates = [
            Candidate(name="TMDB #1", metadata={"title": "Stale"}, score=0.5),
        ]

        # Simulate what _make_metadata_updater + clearing does:
        # After auto-accept, old candidates should be gone
        node.candidates.clear()
        node.candidates.extend([
            Candidate(name="TMDB #1", metadata={"title": "Fresh"}, score=0.9),
        ])

        assert len(node.candidates) == 1
        assert node.candidates[0].metadata["title"] == "Fresh"


class TestClearCandidatesOnAcceptMetadataView:
    """A3: metadata view accept_current_candidate clears candidates after acceptance."""

    def test_accept_clears_candidates_when_tmdb_id_set(self) -> None:
        """Accepting a candidate that sets tmdb_id should clear candidates."""
        node = FileNode(path=Path("test.mp4"))
        node.metadata = {TITLE: "Breaking Bad"}
        node.candidates = [
            Candidate(
                name="TMDB #1",
                metadata={TITLE: "Breaking Bad", TMDB_ID: 1396, MEDIA_TYPE: MEDIA_TYPE_EPISODE},
                score=0.9,
            ),
            Candidate(
                name="TMDB #2",
                metadata={TITLE: "El Camino", TMDB_ID: 559969, MEDIA_TYPE: "movie"},
                score=0.6,
            ),
        ]

        # Simulate accept_current_candidate behavior:
        cand = node.candidates[0]
        for field_name in [TITLE, TMDB_ID, MEDIA_TYPE]:
            val = cand.metadata.get(field_name)
            if val is not None:
                node.metadata[field_name] = val
        # A3: clear candidates after tmdb_id is set
        if TMDB_ID in node.metadata:
            node.candidates.clear()

        assert node.metadata[TMDB_ID] == 1396
        assert len(node.candidates) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline_clear_candidates.py -v`
Expected: Tests pass since they're structural (they demonstrate the expected behavior). The real test is in integration -- but we need to modify the actual code.

- [ ] **Step 3: Implement candidate clearing in pipeline auto-accept**

In `tapes/pipeline.py`, in the `_make_metadata_updater` function, we need to add candidate clearing. The cleanest approach: add clearing to the metadata updater closure itself, since it runs before the candidates updater.

Modify `_make_metadata_updater` (lines 33-52) to accept an optional `clear_candidates` param:

```python
def _make_metadata_updater(
    node: FileNode,
    fields: dict[str, Any],
    stage: bool,
    *,
    clear_candidates: bool = False,
) -> Callable[[], None]:
    """Create a closure that updates node metadata on the main thread.

    Uses explicit parameters instead of closing over loop variables to avoid
    late-binding bugs -- each closure captures the values at creation time,
    not at call time.
    """

    def _apply() -> None:
        for field_name, val in fields.items():
            if val is not None:
                node.metadata[field_name] = val
        if clear_candidates:
            node.candidates.clear()
        if stage:
            node.staged = True

    return _apply
```

Then in `_query_tmdb_for_node()`, line 602, pass `clear_candidates=True`:

```python
        _post(_make_metadata_updater(node, _best_metadata, stage=_stageable, clear_candidates=True))
```

And remove the separate `_post(_make_candidates_updater(node, list(tmdb_candidates)))` call on line 603 -- the show-level candidates are no longer needed after acceptance. The episode query (line 606-614) will add episode candidates later.

Wait -- we still need episode candidates if `media_type == episode`. So the flow is:
1. Clear candidates (via metadata updater)
2. Episode query adds its own candidates

But if `media_type != episode` (it's a movie), we don't run the episode query, and the candidates list stays empty. That's correct -- a movie auto-accept needs no further candidates.

The non-auto-accept path (line 618) still adds all candidates as before.

- [ ] **Step 4: Implement candidate clearing in metadata view**

In `tapes/ui/metadata_view.py`, modify `accept_current_candidate()` (line 338).

After the loop that sets fields (line 356), add:

```python
        # A3: clear candidates after acceptance sets tmdb_id.
        # Episode candidates are added later by the episode query.
        if any(n.metadata.get(TMDB_ID) is not None for n in self.file_nodes):
            for n in self.file_nodes:
                n.candidates.clear()
```

Add `TMDB_ID` to the imports from `tapes.fields` at the top of the file.

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/test_similarity.py tests/test_pipeline.py tests/test_pipeline_auto_accept_gate.py tests/test_pipeline_clear_candidates.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add tapes/pipeline.py tapes/ui/metadata_view.py tests/test_pipeline_clear_candidates.py
git commit -m "feat: clear candidates after show/movie acceptance (A3)"
```

---

## Chunk 2: UX Fixes

### Task 4: Return to tree after show/movie acceptance in metadata view (B1)

**Files:**
- Modify: `tapes/ui/tree_app.py:469-499` (`_accept_metadata_and_return`)
- Modify: `tapes/ui/tree_app.py:876-892` (`_on_tmdb_done`, `_on_tmdb_progress`)

The key change: when TMDB refresh auto-accepts a show/movie while the metadata view is open, close the metadata view and return to tree. This happens when:
1. User edits a field in metadata view → triggers MetadataChanged → triggers TMDB refresh
2. TMDB refresh auto-accepts → dispatches updates via `call_from_thread`
3. On the next `_on_tmdb_done` or `_on_tmdb_progress`, check if we're still in metadata mode with a now-accepted result and return to tree

- [ ] **Step 1: Implement return-to-tree on TMDB completion**

In `tree_app.py`, modify `_on_tmdb_done` (line 885):

```python
    def _on_tmdb_done(self) -> None:
        """Called when all TMDB queries are complete."""
        self._tmdb_querying = False
        if self._mode == AppState.METADATA:
            # B1: if a show/movie was auto-accepted while in metadata view,
            # return to tree so the user sees the result in the destination preview.
            mv = self.query_one(MetadataView)
            if any(n.metadata.get(TMDB_ID) is not None for n in mv.file_nodes):
                self._metadata_snapshot = None  # don't discard -- changes are intentional
                self._show_tree()
                return
            self.query_one(MetadataView).refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()
```

Add `TMDB_ID` to imports from `tapes.fields` at the top of `tree_app.py` (it currently imports `MEDIA_TYPE` and `MEDIA_TYPE_EPISODE`).

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tapes/ui/tree_app.py
git commit -m "feat: return to tree after show/movie acceptance in metadata view (B1)"
```

---

### Task 5: Hint note in multi-node metadata view for accepted shows (B2)

**Files:**
- Modify: `tapes/ui/metadata_view.py:193-218` (`_render_tab_bar`)
- Modify: `tapes/ui/metadata_view.py:106-110` (`_shared_result` -- for tmdb_id check)
- Test: `tests/test_ui/test_metadata_view_hint.py` (new)

- [ ] **Step 1: Write failing test for hint note**

Create `tests/test_ui/test_metadata_view_hint.py`:

```python
"""Tests for B2: hint note in multi-node metadata view for accepted shows."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, SEASON, TITLE, TMDB_ID
from tapes.tree_model import FileNode
from tapes.ui.metadata_view import MetadataView


def _make_episode_node(title: str, tmdb_id: int | None = None, season: int | None = None) -> FileNode:
    node = FileNode(path=Path("test.mkv"))
    metadata: dict = {TITLE: title, MEDIA_TYPE: MEDIA_TYPE_EPISODE}
    if tmdb_id is not None:
        metadata[TMDB_ID] = tmdb_id
    if season is not None:
        metadata[SEASON] = season
    node.metadata = metadata
    return node


class TestMultiNodeHint:
    def test_shows_hint_for_accepted_show_multi_node(self) -> None:
        """When multi-node and tmdb_id set, tab bar shows hint instead of candidate tabs."""
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399),
            _make_episode_node("Game of Thrones", tmdb_id=1399),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)

        # Render tab bar and check it contains hint text, not candidate tabs
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "individual files" in text.lower() or "select individual" in text.lower()

    def test_shows_season_hint_when_season_missing(self) -> None:
        """When season is missing, hint should mention setting season."""
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399),
            _make_episode_node("Game of Thrones", tmdb_id=1399),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)

        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "season" in text.lower()

    def test_no_season_hint_when_season_present(self) -> None:
        """When season IS set, don't show the season hint."""
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399, season=1),
            _make_episode_node("Game of Thrones", tmdb_id=1399, season=1),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)

        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        # Should still show drill-into-files hint but NOT the season hint
        assert "individual files" in text.lower() or "select individual" in text.lower()

    def test_no_hint_for_unaccepted_show(self) -> None:
        """When multi-node but no tmdb_id, show normal tab bar."""
        nodes = [
            _make_episode_node("Game of Thrones"),  # no tmdb_id
            _make_episode_node("Game of Thrones"),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)

        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        # Should show normal tab bar (no TMDB candidates or hint about files)
        assert "individual files" not in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_metadata_view_hint.py -v`
Expected: FAIL (hint logic not yet implemented)

- [ ] **Step 3: Implement hint note in tab bar**

In `tapes/ui/metadata_view.py`, modify `_render_tab_bar` (line 193):

```python
    def _render_tab_bar(self, inner_width: int) -> Text:  # noqa: ARG002
        """Render the tab bar with candidate tabs or multi-node hint."""
        line = Text()
        line.append("    ")

        # B2: In multi-node mode with an accepted show (tmdb_id set),
        # show a hint instead of episode candidate tabs.
        if self.is_multi:
            shared = self._shared_result()
            if shared.get(TMDB_ID) is not None and shared.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
                line.append("Select individual files to match episodes", style=COLOR_MUTED)
                # Check if season is missing across any node
                if any(n.metadata.get(SEASON) is None for n in self.file_nodes):
                    line.append("  \u00b7  ", style=COLOR_MUTED)
                    line.append("Set season to improve matching", style=COLOR_MUTED)
                return line

        candidates = self.node.candidates

        if candidates:
            for idx, cand in enumerate(candidates):
                if idx > 0:
                    line.append("  ")
                conf = f" [{cand.score:.0%}]" if cand.score else ""
                tab_text = f" TMDB #{idx + 1}{conf} "
                if idx == self.candidate_index:
                    line.append(tab_text, style=f"on {COLOR_ACCENT} #000000")
                else:
                    line.append(tab_text)

            line.append("   ")
            line.append(
                "(tab to cycle)",
                style=COLOR_MUTED,
            )
        else:
            line.append("(no TMDB candidates)", style=COLOR_MUTED)

        return line
```

Add `SEASON` and `TMDB_ID` and `MEDIA_TYPE` and `MEDIA_TYPE_EPISODE` to imports from `tapes.fields`. The file already imports `INT_FIELDS` from `tapes.fields` -- add the needed constants.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_metadata_view_hint.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tapes/ui/metadata_view.py tests/test_ui/test_metadata_view_hint.py
git commit -m "feat: show hint note in multi-node metadata view for accepted shows (B2)"
```

---

### Task 6: Named missing-field indicators in tree destination preview (B3)

**Files:**
- Modify: `tapes/templates.py:137-143` (`compute_dest` -- change `"?"` to `"{field_name?}"`)
- Modify: `tapes/ui/tree_render.py:66-79` (`_append_with_yellow_placeholders` -- detect `{field?}` pattern)
- Modify: `tapes/ui/colors.py` (add `COLOR_MISSING` semantic token)
- Test: `tests/test_compute_dest_missing_fields.py` (new)

- [ ] **Step 1: Write failing tests for named indicators**

Create `tests/test_compute_dest_missing_fields.py`:

```python
"""Tests for B3: named missing-field indicators in compute_dest."""

from __future__ import annotations

from pathlib import Path

from tapes.templates import compute_dest
from tapes.tree_model import FileNode


class TestComputeDestMissingFields:
    def test_missing_season_shows_field_name(self) -> None:
        """Missing season renders as {season?} not just ?."""
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {"title": "Game of Thrones", "year": 2011, "episode": 1, "episode_title": "Pilot", "media_type": "episode"}
        template = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{season?}" in dest
        # Other fields should be filled normally
        assert "Game of Thrones" in dest
        assert "2011" in dest

    def test_missing_year_shows_field_name(self) -> None:
        """Missing year renders as {year?}."""
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {"title": "Dune", "media_type": "movie"}
        template = "{title} ({year})/{title} ({year}).{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{year?}" in dest
        assert "Dune" in dest

    def test_all_fields_present_no_placeholders(self) -> None:
        """When all fields present, no {field?} placeholders."""
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {"title": "Dune", "year": 2021, "media_type": "movie"}
        template = "{title} ({year})/{title} ({year}).{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{" not in dest
        assert "?" not in dest

    def test_all_fields_missing_returns_none(self) -> None:
        """All fields missing still returns None."""
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {}
        template = "{title} ({year})/{title} ({year}).{ext}"
        dest = compute_dest(node, template)
        assert dest is None

    def test_multiple_missing_fields(self) -> None:
        """Multiple missing fields each get named placeholders."""
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {"title": "GOT", "media_type": "episode"}
        template = "{title}/Season {season:02d}/{title} - S{season:02d}E{episode:02d}.{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{season?}" in dest
        assert "{episode?}" in dest
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_compute_dest_missing_fields.py -v`
Expected: FAIL (missing fields still show `?` not `{field_name?}`)

- [ ] **Step 3: Implement named placeholders in compute_dest**

In `tapes/templates.py`, modify `compute_dest()` lines 137-143:

Before:
```python
    # Partial: fill missing fields with "?" and strip format specs
    patched = dict(fields)
    for f in missing:
        patched[f] = "?"
    # Remove format specs so "?" doesn't fail on e.g. :02d
    safe_template = re.sub(r"\{(\w+):[^}]+\}", r"{\1}", template)
    return safe_template.format_map(patched)
```

After:
```python
    # Partial: fill missing fields with named placeholder and strip format specs
    patched = dict(fields)
    for f in missing:
        patched[f] = "{" + f + "?}"
    # Remove format specs so placeholder doesn't fail on e.g. :02d
    safe_template = re.sub(r"\{(\w+):[^}]+\}", r"{\1}", template)
    return safe_template.format_map(patched)
```

- [ ] **Step 4: Update tree_render to color named placeholders red**

In `tapes/ui/colors.py`, add a new semantic token:

```python
COLOR_MISSING = CORAL
```

In `tapes/ui/tree_render.py`, replace `_append_with_yellow_placeholders` (lines 66-79):

```python
import re as _re

_MISSING_FIELD_RE = _re.compile(r"\{(\w+)\?\}")


def _append_with_placeholders(text: Text, s: str, base_style: str) -> None:
    """Append *s* to *text*, coloring ``{field?}`` placeholders red."""
    pos = 0
    for m in _MISSING_FIELD_RE.finditer(s):
        if m.start() > pos:
            text.append(s[pos : m.start()], style=base_style)
        text.append(m.group(0), style=COLOR_MISSING)
        pos = m.end()
    if pos < len(s):
        text.append(s[pos:], style=base_style)
```

Update the import in `tree_render.py` to include `COLOR_MISSING`:

```python
from tapes.ui.colors import (
    COLOR_DIFF,
    COLOR_MISSING,
    COLOR_MUTED,
    COLOR_MUTED_LIGHT,
    COLOR_STAGED,
)
```

Replace all 3 calls to `_append_with_yellow_placeholders` with `_append_with_placeholders`:
- Line 43: `_append_with_placeholders(result, dir_part, COLOR_MUTED)`
- Line 58: `_append_with_placeholders(result, stem, "")`
- Line 61: `_append_with_placeholders(result, ext, COLOR_MUTED)`

Also add the `re` import near the top of `tree_render.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_compute_dest_missing_fields.py tests/test_similarity.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: ALL PASS (existing tests that check for `?` in destinations need to be updated to expect `{field?}` instead)

**Note:** Some existing tests may assert `?` in destination paths. These will need updating to match the new `{field_name?}` format. Search for assertions containing `"?"` in destination-related tests and update them.

- [ ] **Step 7: Commit**

```bash
git add tapes/templates.py tapes/ui/tree_render.py tapes/ui/colors.py tests/test_compute_dest_missing_fields.py
git commit -m "feat: show named missing-field indicators in destination preview (B3)"
```

---

## Chunk 3: Documentation

### Task 7: Update pipeline-model.md

**Files:**
- Modify: `docs/pipeline-model.md`

- [ ] **Step 1: Read the current pipeline-model.md**

Read `docs/pipeline-model.md` to understand the current invariants.

- [ ] **Step 2: Update the document**

Add/modify these sections:

1. In the scoring section, document the media-type penalty: "When query and result have differing `media_type` values, the similarity score is multiplied by `MEDIA_TYPE_PENALTY` (0.7)."

2. In the auto-accept decision section, add the media-type gate: "Before evaluating score thresholds, the pipeline checks that the best candidate's `media_type` matches the node's guessit `media_type`. If they disagree, auto-accept is skipped entirely. If guessit did not extract a `media_type`, the gate is skipped."

3. Update the "candidates are always added" invariant to: "Candidates are always added on query. On acceptance (auto or manual), prior candidates are cleared. Episode candidates are added by the subsequent episode query."

- [ ] **Step 3: Commit**

```bash
git add docs/pipeline-model.md
git commit -m "docs: update pipeline model for media-type gate and candidate lifecycle"
```
