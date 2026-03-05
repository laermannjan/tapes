from dataclasses import dataclass, field
from enum import Enum


class CollisionType(str, Enum):
    TEMPLATE_ONLY = "template_only"
    LIKELY_DUPLICATE = "likely_duplicate"


@dataclass
class Collision:
    type: CollisionType
    dest: str
    files: list[dict]
    diff_fields: list[str] = field(default_factory=list)


_TECH_FIELDS = ["resolution", "hdr", "codec", "audio", "media_source", "size"]


def detect_collisions(planned: list[dict], existing_paths: set[str]) -> list[Collision]:
    by_dest: dict[str, list[dict]] = {}
    for item in planned:
        by_dest.setdefault(item["dest"], []).append(item)

    collisions = []
    for dest, items in by_dest.items():
        if len(items) < 2 and dest not in existing_paths:
            continue
        if dest in existing_paths and len(items) == 1:
            collisions.append(Collision(type=CollisionType.TEMPLATE_ONLY, dest=dest, files=items))
            continue
        if len(items) >= 2:
            diff = _find_diff_fields(items)
            col_type = CollisionType.LIKELY_DUPLICATE if not diff else CollisionType.TEMPLATE_ONLY
            collisions.append(Collision(type=col_type, dest=dest, files=items, diff_fields=diff))

    return collisions


_SIZE_TOLERANCE = 0.05  # 5% difference is considered the same release


def _find_diff_fields(items: list[dict]) -> list[str]:
    diff = []
    for f in _TECH_FIELDS:
        if f == "size":
            if _sizes_differ(items):
                diff.append(f)
        else:
            values = {i.get(f) for i in items}
            if len(values) > 1:
                diff.append(f)
    return diff


def _sizes_differ(items: list[dict]) -> bool:
    sizes = [i.get("size") for i in items if i.get("size") is not None]
    if len(sizes) < 2:
        return False
    max_size = max(sizes)
    min_size = min(sizes)
    if max_size == 0:
        return False
    return (max_size - min_size) / max_size > _SIZE_TOLERANCE
