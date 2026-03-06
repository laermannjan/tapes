"""Render a GridRow as a Rich Text line with fixed-width columns."""
from __future__ import annotations

from pathlib import PurePosixPath

from rich.text import Text

from tapes.ui.models import GridRow, RowKind, RowStatus

COL_WIDTHS: dict[str, int] = {
    "status": 5,
    "filepath": 52,
    "title": 16,
    "year": 6,
    "season": 4,
    "episode": 4,
    "episode_title": 32,
}

FIELD_COLS: list[str] = ["title", "year", "season", "episode", "episode_title"]

_BADGE_STYLES: dict[RowStatus, tuple[str, str]] = {
    RowStatus.RAW: ("..", "#555555"),
    RowStatus.AUTO: ("**", "#55aa99"),
    RowStatus.UNCERTAIN: ("??", "#ccaa33"),
    RowStatus.EDITED: ("!!", "#a78bfa"),
    RowStatus.FROZEN: ("--", "#66cccc"),
}

BG_ROW_CUR = "#1e1e1e"
BG_COL_HI = "#1e1e1e"
BG_CELL_CUR = "#2c2c2c"
BG_CELL_SEL = "#3a5a3a"
BG_ROW_SEL = "#1a241a"
BG_CELL_SEL_CUR = "#4a6a4a"

# When text sits on a selected (green) background, boost dim colors for readability.
_SEL_TEXT: dict[str, str] = {
    "#555555": "#999999",
    "#888888": "#cccccc",
    "#dddddd": "#eeeeee",
    "#55aa99": "#77ccbb",
    "#a78bfa": "#c4a8ff",
    "#66cccc": "#88eeee",
}


def _pad(text: str, width: int) -> str:
    """Pad or truncate text to exact column width."""
    if len(text) > width:
        return text[: width - 1] + "\u2026"
    return text + " " * (width - len(text))


def _col(t: Text, value: str, width: int, style: str, bg: str | None = None) -> None:
    """Append a fixed-width column to a Text object."""
    padded = _pad(value, width)
    full_style = f"{style} on {bg}" if bg else style
    t.append(padded, style=full_style)


def render_row(
    row: GridRow,
    cursor_col: int | None,
    is_cursor_row: bool,
    *,
    selected_cols: set[int] | None = None,
    is_sel_cursor_row: bool = False,
    edit_col: int | None = None,
    edit_value: str | None = None,
) -> Text:
    """Render a single GridRow as a Rich Text line."""
    if selected_cols is None:
        selected_cols = set()

    t = Text()

    if row.kind == RowKind.BLANK:
        _col(t, "", COL_WIDTHS["status"], "#333333")
        _col(t, "", COL_WIDTHS["filepath"], "#333333")
        for i, col_name in enumerate(FIELD_COLS):
            bg = None
            if i == cursor_col:
                bg = BG_COL_HI
            if i in selected_cols:
                bg = BG_CELL_SEL
            _col(t, "", COL_WIDTHS[col_name], "#333333", bg=bg)
        return t

    if row.kind == RowKind.MATCH:
        row_bg = BG_ROW_CUR if is_cursor_row else None
        # Status: down-arrow indicator
        _col(t, " \u23bf  ", COL_WIDTHS["status"], "#333333", bg=row_bg)
        # Filepath: "(match)" in yellow
        _col(t, "(match)", COL_WIDTHS["filepath"], "#ccaa33", bg=row_bg)
        # Metadata columns: proposed values in cyan
        fields = row.match_fields
        match_values = [
            str(fields.get("title", "")),
            str(fields.get("year", "")) if fields.get("year") else "",
            str(fields.get("season", "")) if fields.get("season") else "",
            str(fields.get("episode", "")) if fields.get("episode") else "",
            str(fields.get("episode_title", "")),
        ]
        for i, (col_name, value) in enumerate(zip(FIELD_COLS, match_values)):
            bg = row_bg
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

    is_comp = row.is_companion
    base_style = "#555555" if is_comp else "#888888"
    bright_style = "#888888" if is_comp else "#dddddd"

    row_bg = None
    if is_cursor_row:
        row_bg = BG_ROW_CUR
    elif any(i in selected_cols for i in range(len(FIELD_COLS))):
        row_bg = BG_ROW_SEL

    # Status badge in brackets: [..] [**] [!!] [--]
    badge_text, badge_style = _BADGE_STYLES.get(row.status, ("..", "#555555"))
    bracket_style = f"#333333 on {row_bg}" if row_bg else "#333333"
    badge_full_style = f"{badge_style} on {row_bg}" if row_bg else badge_style
    pad_style = f"on {row_bg}" if row_bg else ""
    t.append("[", style=bracket_style)
    t.append(badge_text, style=badge_full_style)
    t.append("]", style=bracket_style)
    t.append(" ", style=pad_style)

    # Filepath column
    fp = row.filepath
    p = PurePosixPath(fp)
    if len(p.parts) > 1 and row.is_video:
        dir_part = str(p.parent) + "/"
        name_part = p.name
        padded_fp = _pad(dir_part + name_part, COL_WIDTHS["filepath"])
        fp_text = Text()
        # Directory part in dim
        dir_len = min(len(dir_part), len(padded_fp))
        fp_text.append(
            padded_fp[:dir_len],
            style=f"#555555 on {row_bg}" if row_bg else "#555555",
        )
        # Filename part in bright
        remaining = padded_fp[dir_len:]
        fp_text.append(
            remaining,
            style=f"{bright_style} on {row_bg}" if row_bg else bright_style,
        )
        t.append_text(fp_text)
    else:
        style = base_style if is_comp else bright_style
        _col(t, fp, COL_WIDTHS["filepath"], style, bg=row_bg)

    # Metadata columns
    values = [
        row.title or "",
        str(row.year) if row.year else "",
        str(row.season) if row.season is not None else "",
        str(row.episode) if row.episode is not None else "",
        row.episode_title or "",
    ]

    for i, (col_name, value) in enumerate(zip(FIELD_COLS, values)):
        # Determine base text style
        if col_name in row.frozen_fields:
            style = "#66cccc"
        elif row.status == RowStatus.EDITED and col_name in row.edited_fields:
            style = "#a78bfa"
        elif row.status == RowStatus.AUTO:
            style = "#55aa99" if value else base_style
        else:
            style = base_style if is_comp else (bright_style if value else base_style)

        bg = row_bg
        if is_cursor_row and i == cursor_col:
            bg = BG_CELL_CUR
        elif i == cursor_col:
            bg = BG_COL_HI
        if i in selected_cols:
            if is_sel_cursor_row and i == cursor_col:
                bg = BG_CELL_SEL_CUR
                style = _SEL_TEXT.get(style, style)
            else:
                bg = BG_CELL_SEL
                style = _SEL_TEXT.get(style, style)

        # Inline edit: show edit buffer instead of actual value
        display_value = value
        display_style = style
        if is_cursor_row and edit_col is not None and i == edit_col:
            display_value = edit_value if edit_value is not None else ""
            display_style = f"underline {style}"

        _col(t, display_value, COL_WIDTHS[col_name], display_style, bg=bg)

    return t
