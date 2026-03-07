"""Auto-pipeline: populate sources and auto-accept confident matches."""
from __future__ import annotations

from typing import Any

from tapes.similarity import compute_confidence
from tapes.ui.tree_model import FileNode, Source, TreeModel


def run_auto_pipeline(
    model: TreeModel, confidence_threshold: float | None = None
) -> None:
    """Populate sources and auto-accept confident matches.

    For each file node:
    1. Extract metadata from filename via guessit -> result + "from filename" source
    2. Query mock TMDB -> add "TMDB #1" source
    3. If TMDB confidence >= threshold, apply TMDB fields to result and auto-stage
    """
    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
    from tapes.metadata import extract_metadata
    from tapes.ui.query import mock_tmdb_lookup

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    for node in model.all_files():
        _populate_node(node, confidence_threshold, extract_metadata, mock_tmdb_lookup)


def refresh_tmdb_source(
    node: FileNode, confidence_threshold: float | None = None
) -> None:
    """Re-query mock TMDB for a file and update its sources.

    Uses the node's current result title/episode for the query.
    Removes existing TMDB sources, adds new one if found.
    Auto-accepts if confidence >= threshold.
    """
    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
    from tapes.ui.query import mock_tmdb_lookup

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    title = str(node.result.get("title", ""))
    episode = node.result.get("episode")
    tmdb_result = mock_tmdb_lookup(title, episode=episode)

    # Remove existing TMDB sources
    node.sources = [s for s in node.sources if not s.name.startswith("TMDB")]

    if tmdb_result is not None:
        fields, _mock_confidence = tmdb_result
        confidence = compute_confidence(node.result, fields)
        tmdb_source = Source(name="TMDB #1", fields=fields, confidence=confidence)
        node.sources.append(tmdb_source)

        if confidence >= confidence_threshold:
            for field, val in fields.items():
                if val is not None:
                    node.result[field] = val


def _populate_node(
    node: FileNode,
    confidence_threshold: float,
    extract_metadata_fn: object,
    mock_tmdb_lookup_fn: object,
) -> None:
    """Populate a single node with sources and auto-accept if confident."""
    # 1. Guessit: extract metadata from filename
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

    # Set result from guessit
    node.result = dict(filename_fields)

    # Create "from filename" source
    filename_source = Source(name="from filename", fields=filename_fields)
    node.sources = [filename_source]

    # 2. TMDB lookup
    title = node.result.get("title", "")
    episode = node.result.get("episode")
    tmdb_result = mock_tmdb_lookup_fn(str(title), episode=episode)  # type: ignore[operator]
    if tmdb_result is not None:
        tmdb_fields, _mock_confidence = tmdb_result
        confidence = compute_confidence(node.result, tmdb_fields)
        tmdb_source = Source(
            name="TMDB #1",
            fields=tmdb_fields,
            confidence=confidence,
        )
        node.sources.append(tmdb_source)

        # 3. Auto-accept if confident
        if confidence >= confidence_threshold:
            for field, val in tmdb_fields.items():
                if val is not None:
                    node.result[field] = val
            node.staged = True
