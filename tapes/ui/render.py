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
    RowStatus.RAW: ("..", "#555"),
    RowStatus.AUTO: ("**", "#5a9"),
    RowStatus.UNCERTAIN: ("??", "#ca3"),
    RowStatus.EDITED: ("!!", "#a78bfa"),
}

BG_ROW_CUR = "#1e1e1e"
BG_COL_HI = "#1e1e1e"
BG_CELL_CUR = "#2c2c2c"
BG_CELL_SEL = "#363636"
BG_ROW_SEL = "#1c1c1c"
BG_CELL_SEL_CUR = "#3c3c3c"


def _pad(text: str, width: int) -> str:
    """Pad or truncate text to exact column width."""
    if len(text) >= width:
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
) -> Text:
    """Render a single GridRow as a Rich Text line."""
    if selected_cols is None:
        selected_cols = set()

    t = Text()

    if row.kind == RowKind.BLANK:
        _col(t, "", COL_WIDTHS["status"], "#333")
        _col(t, "", COL_WIDTHS["filepath"], "#333")
        for i, col_name in enumerate(FIELD_COLS):
            bg = None
            if i == cursor_col:
                bg = BG_COL_HI
            if i in selected_cols:
                bg = BG_CELL_SEL
            _col(t, "", COL_WIDTHS[col_name], "#333", bg=bg)
        return t

    is_comp = row.is_companion
    base_style = "#555" if is_comp else "#888"
    bright_style = "#888" if is_comp else "#ddd"

    row_bg = None
    if is_cursor_row:
        row_bg = BG_ROW_CUR
    elif any(i in selected_cols for i in range(len(FIELD_COLS))):
        row_bg = BG_ROW_SEL

    # Status badge
    badge_text, badge_style = _BADGE_STYLES.get(row.status, ("..", "#555"))
    _col(
        t,
        badge_text.rjust(COL_WIDTHS["status"] - 1) + " ",
        COL_WIDTHS["status"],
        badge_style,
        bg=row_bg,
    )

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
            style=f"#555 on {row_bg}" if row_bg else "#555",
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
        _col(t, _pad(fp, COL_WIDTHS["filepath"]), COL_WIDTHS["filepath"], style, bg=row_bg)

    # Metadata columns
    values = [
        row.title or "",
        str(row.year) if row.year else "",
        str(row.season) if row.season is not None else "",
        str(row.episode) if row.episode is not None else "",
        row.episode_title or "",
    ]

    for i, (col_name, value) in enumerate(zip(FIELD_COLS, values)):
        if row.status == RowStatus.EDITED and col_name in row.edited_fields:
            style = "#a78bfa"
        elif row.status == RowStatus.AUTO:
            style = "#6bc" if value else base_style
        else:
            style = base_style if is_comp else (bright_style if value else base_style)

        bg = row_bg
        if is_cursor_row and i == cursor_col:
            bg = BG_CELL_CUR
            style = "#fff"
        elif i == cursor_col:
            bg = BG_COL_HI
        if i in selected_cols:
            if is_sel_cursor_row and i == cursor_col:
                bg = BG_CELL_SEL_CUR
                style = "#fff"
            else:
                bg = BG_CELL_SEL

        _col(t, value, COL_WIDTHS[col_name], style, bg=bg)

    return t
