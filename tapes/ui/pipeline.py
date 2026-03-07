"""Auto-pipeline: populate sources and auto-accept confident matches."""
from __future__ import annotations

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
    from tapes.metadata import extract_metadata
    from tapes.ui.query import CONFIDENCE_THRESHOLD, mock_tmdb_lookup

    if confidence_threshold is None:
        confidence_threshold = CONFIDENCE_THRESHOLD

    for node in model.all_files():
        _populate_node(node, confidence_threshold, extract_metadata, mock_tmdb_lookup)


def _populate_node(
    node: FileNode,
    confidence_threshold: float,
    extract_metadata_fn: object,
    mock_tmdb_lookup_fn: object,
) -> None:
    """Populate a single node with sources and auto-accept if confident."""
    from typing import Any

    # 1. Guessit: extract metadata from filename
    meta = extract_metadata_fn(node.path.name)  # type: ignore[operator]
    filename_fields: dict[str, Any] = {}
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
        tmdb_fields, confidence = tmdb_result
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
