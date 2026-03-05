import re
import shlex

from tapes.db.repository import Repository, ItemRecord

# Columns in the items table that can be queried
_VALID_FIELDS = {
    "path", "media_type", "tmdb_id", "title", "year", "show", "season",
    "episode", "episode_title", "director", "genre", "edition", "codec",
    "resolution", "audio", "hdr", "match_source", "confidence",
}

_NUMERIC_FIELDS = {"year", "season", "episode", "tmdb_id", "hdr", "confidence"}

_RANGE_OP = re.compile(r"^(>=?|<=?)(.+)$")


class LibraryService:
    def __init__(self, repo: Repository):
        self._repo = repo

    def query(self, query_str: str) -> list[ItemRecord]:
        query_str = query_str.strip()
        if not query_str:
            return self._repo.get_all_items()

        tokens = shlex.split(query_str)
        clauses: list[str] = []
        params: list = []

        for token in tokens:
            if ":" in token:
                field, _, value = token.partition(":")
                if field not in _VALID_FIELDS:
                    clauses.append("0")  # impossible clause
                    continue
                self._parse_field_query(field, value, clauses, params)
            else:
                # Bare word: search title, show, director, episode_title
                clauses.append(
                    "(title LIKE ? OR show LIKE ? OR director LIKE ? OR episode_title LIKE ?)"
                )
                pattern = f"%{token}%"
                params.extend([pattern, pattern, pattern, pattern])

        if not clauses:
            return self._repo.get_all_items()

        where = " AND ".join(clauses)
        rows = self._repo._conn.execute(
            f"SELECT * FROM items WHERE {where}", params
        ).fetchall()
        return [_row_to_item(r) for r in rows]

    def _parse_field_query(
        self, field: str, value: str, clauses: list[str], params: list
    ) -> None:
        m = _RANGE_OP.match(value)
        if m and field in _NUMERIC_FIELDS:
            op, val = m.group(1), m.group(2)
            clauses.append(f"{field} {op} ?")
            params.append(_coerce_numeric(val))
        elif field in _NUMERIC_FIELDS:
            clauses.append(f"{field} = ?")
            params.append(_coerce_numeric(value))
        else:
            clauses.append(f"{field} = ? COLLATE NOCASE")
            params.append(value)


def _coerce_numeric(val: str) -> int | float:
    try:
        return int(val)
    except ValueError:
        return float(val)


def _row_to_item(row) -> ItemRecord:
    if hasattr(row, "keys"):
        return ItemRecord(**{k: row[k] for k in row.keys()})
    return ItemRecord(*row)
