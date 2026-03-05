"""Dict-based group merging using composite keys."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from tapes.models import GroupType, ImportGroup

MergeCriterion = Callable[[list[ImportGroup]], list[ImportGroup]]


def same_season(groups: list[ImportGroup]) -> list[ImportGroup]:
    """Merge groups with same (title.lower(), season) for episodes."""
    buckets: dict[tuple[str, int], list[ImportGroup]] = defaultdict(list)
    passthrough: list[ImportGroup] = []

    for g in groups:
        meta = g.metadata
        if (
            meta.media_type == "episode"
            and meta.title is not None
            and meta.season is not None
        ):
            key = (meta.title.lower(), meta.season)
            buckets[key].append(g)
        else:
            passthrough.append(g)

    result = list(passthrough)
    for bucket in buckets.values():
        if len(bucket) == 1:
            result.append(bucket[0])
        else:
            merged = ImportGroup(metadata=bucket[0].metadata)
            for g in bucket:
                for f in g.files:
                    merged.add_file(f)
            merged.group_type = GroupType.SEASON
            result.append(merged)
    return result


def same_multi_part(groups: list[ImportGroup]) -> list[ImportGroup]:
    """Merge groups with same title.lower() where both have part values."""
    buckets: dict[str, list[ImportGroup]] = defaultdict(list)
    passthrough: list[ImportGroup] = []

    for g in groups:
        meta = g.metadata
        if meta.title is not None and meta.part is not None:
            key = meta.title.lower()
            buckets[key].append(g)
        else:
            passthrough.append(g)

    result = list(passthrough)
    for bucket in buckets.values():
        if len(bucket) == 1:
            result.append(bucket[0])
        else:
            merged = ImportGroup(metadata=bucket[0].metadata)
            for g in bucket:
                for f in g.files:
                    merged.add_file(f)
            merged.group_type = GroupType.MULTI_PART
            result.append(merged)
    return result


def group_files(
    groups: list[ImportGroup],
    criteria: list[MergeCriterion] | None = None,
) -> list[ImportGroup]:
    """Apply merge criteria sequentially (default: [same_season, same_multi_part])."""
    if criteria is None:
        criteria = [same_season, same_multi_part]
    for criterion in criteria:
        groups = criterion(groups)
    return groups
