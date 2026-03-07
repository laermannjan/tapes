"""Auto-pipeline: populate sources and auto-accept confident matches."""
from __future__ import annotations

import logging
from typing import Any

from tapes.similarity import compute_confidence, compute_episode_confidence
from tapes.ui.tree_model import FileNode, Source, TreeModel

logger = logging.getLogger(__name__)


def run_auto_pipeline(
    model: TreeModel,
    token: str = "",
    confidence_threshold: float | None = None,
) -> None:
    """Populate sources and auto-accept confident matches.

    For each file node:
    1. Extract metadata from filename via guessit -> result + "from filename" source
    2. Query TMDB (two-stage: show/movie, then episodes) -> add TMDB sources
    3. If TMDB confidence >= threshold, apply TMDB fields to result and auto-stage
    """
    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
    from tapes.metadata import extract_metadata

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    for node in model.all_files():
        _populate_node_guessit(node, extract_metadata)
        _query_tmdb_for_node(node, token, confidence_threshold)


def refresh_tmdb_source(
    node: FileNode,
    token: str = "",
    confidence_threshold: float | None = None,
) -> None:
    """Re-query TMDB for a file and update its sources.

    Uses the node's current result title/year for the query.
    Removes existing TMDB sources, adds new ones if found.
    Auto-accepts if confidence >= threshold.
    """
    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    # Remove existing TMDB sources
    node.sources = [s for s in node.sources if not s.name.startswith("TMDB")]

    _query_tmdb_for_node(node, token, confidence_threshold)


def _populate_node_guessit(node: FileNode, extract_metadata_fn: object) -> None:
    """Extract metadata from filename via guessit and set as result + source."""
    meta = extract_metadata_fn(node.path.name)  # type: ignore[operator]
    filename_fields: dict = {}
    if meta.title:
        filename_fields["title"] = meta.title
    if meta.year is not None:
        filename_fields["year"] = meta.year
    if meta.season is not None:
        filename_fields["season"] = meta.season
    if meta.episode is not None:
        filename_fields["episode"] = meta.episode
    if meta.media_type:
        filename_fields["media_type"] = meta.media_type
    # Add raw fields (codec, media_source, etc.)
    for k, v in meta.raw.items():
        if v is not None:
            filename_fields[k] = v

    node.result = dict(filename_fields)
    filename_source = Source(name="from filename", fields=filename_fields)
    node.sources = [filename_source]


def _query_tmdb_for_node(
    node: FileNode, token: str, threshold: float
) -> None:
    """Two-stage TMDB query for a single node.

    Stage 1: Find movie/show
    - search_multi with title (+year if available) -> up to 3 Sources
    - Auto-accept: if best Source confidence >= threshold, apply to result
    - If accepted media_type == "movie": done

    Stage 2: Find episode (only if stage 1 accepted a TV show)
    - If season in result: fetch that season's episodes
    - Score episodes against result, create Sources with full fields
    - If no auto-accept from that season: try all other seasons
    - If still no auto-accept: keep top 3 episode Sources
    - Auto-accept best episode if confident
    """
    from tapes import tmdb

    if not token:
        return

    title = str(node.result.get("title", ""))
    if not title:
        return

    year = node.result.get("year")

    # Stage 1: search for movie/show
    search_results = tmdb.search_multi(title, token, year=year)

    if not search_results:
        return

    # Create sources for each search result
    tmdb_sources: list[Source] = []
    for i, sr in enumerate(search_results[:3]):
        confidence = compute_confidence(node.result, sr)
        source = Source(
            name=f"TMDB #{i + 1}",
            fields=dict(sr),
            confidence=confidence,
        )
        tmdb_sources.append(source)

    # Find best source
    best = max(tmdb_sources, key=lambda s: s.confidence)

    if best.confidence >= threshold:
        # Auto-accept: apply non-empty fields to result
        for field, val in best.fields.items():
            if val is not None:
                node.result[field] = val
        node.staged = True

        # Stage 2: if TV show, fetch episodes
        if best.fields.get("media_type") == "episode":
            _query_episodes(node, token, threshold, best.fields)
            return

    # Add show-level TMDB sources (not episode sources yet)
    node.sources.extend(tmdb_sources)


def _query_episodes(
    node: FileNode, token: str, threshold: float, show_fields: dict
) -> None:
    """Stage 2: fetch episode data for a TV show match."""
    from tapes import tmdb

    show_id = show_fields.get("tmdb_id")
    show_title = show_fields.get("title", "")
    show_year = show_fields.get("year")

    if show_id is None:
        return

    # Get show info to know available seasons
    show_info = tmdb.get_show(show_id, token)
    if not show_info:
        return

    available_seasons = show_info.get("seasons", [])
    query_season = node.result.get("season")

    # Try the query season first, then others
    seasons_to_try: list[int] = []
    if query_season is not None and query_season in available_seasons:
        seasons_to_try.append(query_season)
    # Add remaining seasons
    for s in available_seasons:
        if s not in seasons_to_try:
            seasons_to_try.append(s)

    all_episode_sources: list[Source] = []
    accepted = False

    for season_num in seasons_to_try:
        episodes = tmdb.get_season_episodes(
            show_id, season_num, token,
            show_title=show_title, show_year=show_year,
        )

        for ep in episodes:
            confidence = compute_episode_confidence(node.result, ep)
            source = Source(
                name=f"TMDB #{len(all_episode_sources) + 1}",
                fields=dict(ep),
                confidence=confidence,
            )
            all_episode_sources.append(source)

            if not accepted and confidence >= threshold:
                # Auto-accept this episode
                for field, val in ep.items():
                    if val is not None:
                        node.result[field] = val
                accepted = True

        # If we found a match in the preferred season, stop
        if accepted and season_num == query_season:
            break

    # Keep top 3 episode sources by confidence
    all_episode_sources.sort(key=lambda s: s.confidence, reverse=True)
    top_sources = all_episode_sources[:3]

    # Re-number them
    for i, src in enumerate(top_sources):
        src.name = f"TMDB #{i + 1}"

    node.sources.extend(top_sources)
