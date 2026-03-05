import re

# Windows-illegal characters in filenames (not path separators)
_WINDOWS_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f]')
# Windows reserved names
_WINDOWS_RESERVED = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', re.IGNORECASE
)
# Conditional field syntax: {field: prefix$suffix}
# Note: no \s* after colon — the space is part of the prefix
_CONDITIONAL = re.compile(r'\{(\w+):([^}]*?)\$\s*([^}]*?)\}')
# Standard field syntax: {field} or {field:format}
_STANDARD = re.compile(r'\{(\w+)(?::([^}]*))?\}')


def render_template(
    template: str,
    fields: dict,
    replace: dict[str, str] | None = None,
) -> str:
    """
    Render a path template string with the given fields.

    Syntax:
      {field}                 — plain substitution; empty string if missing
      {field:02d}             — Python format spec
      {field: prefix$suffix}  — conditional: renders 'prefix{value}suffix'
                                only when field is present and non-None/non-empty

    The replace table is applied to each field value before substitution,
    so that characters like "/" in a title don't become path separators.
    """
    _replace = replace or {}

    # Pass 1: conditional fields
    def replace_conditional(m: re.Match) -> str:
        field, prefix, suffix = m.group(1), m.group(2), m.group(3)
        value = fields.get(field)
        if value is None or value == "":
            return ""
        value = _apply_replace(str(value), _replace)
        return f"{prefix}{value}{suffix}"

    result = _CONDITIONAL.sub(replace_conditional, template)

    # Pass 2: standard fields
    def replace_standard(m: re.Match) -> str:
        field, fmt = m.group(1), m.group(2)
        value = fields.get(field)
        if value is None:
            return ""
        if fmt:
            try:
                formatted = format(value, fmt)
            except (ValueError, TypeError):
                formatted = str(value)
        else:
            formatted = str(value)
        return _apply_replace(formatted, _replace)

    result = _STANDARD.sub(replace_standard, result)

    # Pass 3: sanitize each path segment for cross-platform use
    result = sanitize_path(result)

    return result


def sanitize_path(path: str, replace: dict[str, str] | None = None) -> str:
    """
    Sanitize a rendered path string for cross-platform use.
    Path separators (/) are preserved. The optional replace table is applied
    to each segment (for standalone use; render_template applies it per-value).
    """
    segments = path.split("/")
    sanitized = []
    for segment in segments:
        if replace:
            segment = _apply_replace(segment, replace)
        segment = _sanitize_segment(segment)
        sanitized.append(segment)
    return "/".join(sanitized)


def _apply_replace(s: str, replace: dict[str, str]) -> str:
    for pattern, replacement in replace.items():
        s = s.replace(pattern, replacement)
    return s


def _sanitize_segment(segment: str) -> str:
    """Sanitize a single path segment (filename component)."""
    segment = _WINDOWS_ILLEGAL.sub("", segment)
    segment = segment.strip(". ")
    if _WINDOWS_RESERVED.match(segment):
        segment = "_" + segment
    return segment
