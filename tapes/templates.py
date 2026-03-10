"""Pure template and path utilities for file destination computation.

These functions have no Rich/Textual dependency and can be used anywhere
in the codebase (core, CLI, UI).
"""

from __future__ import annotations

import functools
import re
import string
from pathlib import Path
from typing import Any

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE
from tapes.tree_model import FileNode


@functools.lru_cache(maxsize=8)
def template_field_names(template: str) -> list[str]:
    """Extract unique field names referenced in a template string."""
    return list(dict.fromkeys(fname for _, fname, _, _ in string.Formatter().parse(template) if fname is not None))


def select_template(node: FileNode, movie_template: str, tv_template: str) -> str:
    """Select the appropriate template based on the node's media_type.

    Returns ``tv_template`` if ``media_type`` is ``"episode"``,
    otherwise ``movie_template``.
    """
    media_type = node.metadata.get(MEDIA_TYPE)
    if media_type == MEDIA_TYPE_EPISODE:
        return tv_template
    return movie_template


_KNOWN_TAGS = frozenset({"forced", "sdh", "signs", "commentary"})


def _is_tag(s: str) -> bool:
    """Check if a suffix component is a language/subtitle tag."""
    return s.lower() in _KNOWN_TAGS or (len(s) in (2, 3) and s.isalpha())


def full_extension(path: Path) -> str:
    """Return the full extension, preserving tags like '.forced.en.srt'.

    Walks backwards through suffixes, collecting consecutive tags
    (language codes, 'forced', 'sdh', etc.) that precede the final
    extension.  Also picks up hyphen-prefixed tags (e.g. ``-forced``)
    that appear just before the dot-suffix chain in the stem.
    """
    suffixes = path.suffixes
    if not suffixes:
        return ""
    # Always include the last suffix; walk backwards collecting tags
    count = 1
    for i in range(len(suffixes) - 2, -1, -1):
        tag = suffixes[i].lstrip(".")
        if _is_tag(tag):
            count += 1
        else:
            break

    ext = "".join(suffixes[-count:]).lstrip(".")

    # Check for hyphen-prefixed tags in the stem (e.g. "movie-forced")
    stem = path.name[: -len("." + ext)] if ext else path.stem
    while "-" in stem:
        last_hyphen = stem.rfind("-")
        candidate = stem[last_hyphen + 1 :]
        if _is_tag(candidate):
            ext = candidate + "." + ext
            stem = stem[:last_hyphen]
        else:
            break

    return ext


_UNSAFE_PATH_CHARS = re.compile(r'[./\\:*?"<>|\x00-\x1f]')


def _sanitize_field(value: Any) -> Any:
    """Sanitize a template field value for safe use in file paths.

    Replaces characters that are illegal or dangerous in filenames:
    ``. / \\ : * ? " < > |`` and control characters (0x00-0x1F).
    Consecutive underscores from replacements are collapsed.
    Leading/trailing dots, spaces, and underscores are stripped.
    Only applies to string values; integers and other types pass through.
    """
    if not isinstance(value, str):
        return value
    result = _UNSAFE_PATH_CHARS.sub("_", value)
    result = re.sub(r"_+", "_", result)
    return result.strip(". _")


def can_fill_template(node: FileNode, merged_result: dict, movie_template: str, tv_template: str) -> bool:
    """Check if *merged_result* has all fields needed to fill the destination template.

    The ``ext`` field is excluded because it always comes from the filename.
    Returns ``True`` when every other required field is present and non-None.
    """
    template = select_template(node, movie_template, tv_template)
    needed = template_field_names(template)
    return all(merged_result.get(f) is not None for f in needed if f != "ext")


def compute_dest(node: FileNode, template: str) -> str | None:
    """Compute the destination path for a file node using a template.

    Extracts fields from ``node.metadata`` and adds ``ext`` from the file
    suffix. Returns None if any required template field is missing or None.

    Format specs (e.g. ``{season:02d}``) are applied when all fields are
    present. If a field with a format spec is missing, the spec is dropped
    and ``?`` is shown instead so the user can see partial progress.

    String field values are sanitized to remove characters that are illegal
    in filenames (``/ \\ : * ? " < > |`` and control characters).
    """
    fields: dict[str, Any] = {k: _sanitize_field(v) for k, v in node.metadata.items()}
    fields["ext"] = full_extension(node.path)

    needed = template_field_names(template)
    missing = [f for f in needed if fields.get(f) is None]

    if not missing:
        return template.format_map(fields)

    # All fields missing -> no useful destination
    if len(missing) == len(needed):
        return None

    # Partial: fill missing fields with "{field?}" and strip format specs
    patched = dict(fields)
    for f in missing:
        patched[f] = "{" + f + "?}"
    # Remove format specs so "?" doesn't fail on e.g. :02d
    safe_template = re.sub(r"\{(\w+):[^}]+\}", r"{\1}", template)
    return safe_template.format_map(patched)
