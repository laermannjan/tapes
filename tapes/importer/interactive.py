"""Interactive prompt logic and default-action determination.

Determines what the default action should be when presenting identification
results to the user during interactive import mode.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from enum import Enum

from rich.console import Console
from rich.text import Text

from tapes.companions.classifier import Category, CompanionFile

logger = logging.getLogger(__name__)

STRONG_CONFIDENCE = 0.75
GAP_THRESHOLD = 0.2
_EPS = 1e-9  # tolerance for floating-point comparisons


def _int_or_none(s: str) -> int | None:
    """Parse a string as int, returning None on failure."""
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def manual_prompt(
    console: Console,
    *,
    default_media_type: str = "movie",
    default_title: str = "",
    default_year: int | None = None,
) -> "SearchResult":
    """Collect metadata fields directly from the user.

    Returns a synthetic SearchResult with tmdb_id=0 and confidence=1.0.
    """
    from tapes.metadata.base import SearchResult

    year_default = str(default_year) if default_year else ""
    mt = input(f"Media type [movie/tv] ({default_media_type}): ").strip().lower() or default_media_type
    if mt not in ("movie", "tv"):
        mt = default_media_type
    title = input(f"Title ({default_title}): " if default_title else "Title: ").strip() or default_title
    raw_year = input(f"Year (optional) ({year_default}): " if year_default else "Year (optional): ").strip() or year_default
    year = int(raw_year) if raw_year else None

    show = None
    season = None
    episode = None
    episode_title = None

    more = input("More fields? [y/N]: ").strip().lower()
    if more == "y":
        if mt == "tv":
            show = input("Show name: ").strip() or title
            season = _int_or_none(input("Season: ").strip())
            episode = _int_or_none(input("Episode: ").strip())
            episode_title = input("Episode title (optional): ").strip() or None

    return SearchResult(
        tmdb_id=0,
        title=title,
        year=year,
        media_type=mt,
        confidence=1.0,
        show=show,
        season=season,
        episode=episode,
        episode_title=episode_title,
    )


def search_prompt(
    console: Console,
    *,
    default_media_type: str = "movie",
    default_title: str = "",
    default_year: int | None = None,
) -> tuple[str, str, int | None]:
    """Collect structured search fields from the user.

    Returns (media_type, title, year).
    """
    year_default = str(default_year) if default_year else ""
    mt_prompt = f"Media type [movie/tv] ({default_media_type}): "
    title_prompt = f"Title ({default_title}): " if default_title else "Title: "
    year_prompt = f"Year (optional) ({year_default}): " if year_default else "Year (optional): "

    mt = input(mt_prompt).strip().lower() or default_media_type
    if mt not in ("movie", "tv"):
        mt = default_media_type
    title = input(title_prompt).strip() or default_title
    raw_year = input(year_prompt).strip() or year_default
    year = int(raw_year) if raw_year else None

    return mt, title, year


class PromptAction(str, Enum):
    """Actions available at an interactive import prompt."""

    ACCEPT = "accept"
    ACCEPT_ALL = "accept_all"
    SEARCH = "search"
    SKIP = "skip"
    MANUAL = "manual"
    QUIT = "quit"


@dataclass
class InteractivePrompt:
    """Determines the default action for an interactive import prompt.

    The default action is what happens when the user presses Enter without
    making an explicit choice. It is based on the confidence scores of the
    candidates and the context (initial identification vs. search results).

    Design doc table:
        | Situation                                        | Default (Enter) |
        |--------------------------------------------------|-----------------|
        | Single match, strong confidence (>= 0.75)        | Accept          |
        | Single match, big gap to #2 (>= 0.2)             | Accept          |
        | Single match, low confidence                      | Search          |
        | Multiple auto-matched candidates, ambiguous       | Search          |
        | Search results - one dominant result (gap >= 0.2) | Accept #1       |
        | Search results - results are close together       | None            |
        | No match found (first encounter)                  | Search          |
        | No match found (after search returned nothing)    | Skip            |
    """

    candidates: list  # objects with .confidence attribute
    after_failed_search: bool = False
    is_search_result: bool = False

    @property
    def default_action(self) -> PromptAction | None:
        """Return the default action, or None if the user must choose."""
        if not self.candidates:
            if self.after_failed_search:
                return PromptAction.SKIP
            return PromptAction.SEARCH

        top = self.candidates[0].confidence
        has_multiple = len(self.candidates) > 1
        second = self.candidates[1].confidence if has_multiple else 0.0
        gap = top - second

        if self.is_search_result:
            if gap >= GAP_THRESHOLD - _EPS:
                return PromptAction.ACCEPT
            return None  # too close, user must pick

        # Initial identification results
        if top >= STRONG_CONFIDENCE - _EPS:
            return PromptAction.ACCEPT
        if has_multiple and gap >= GAP_THRESHOLD - _EPS:
            return PromptAction.ACCEPT
        if not has_multiple:
            return PromptAction.SEARCH
        return PromptAction.SEARCH


# --- Action key labels and their hotkeys ---

_ACTION_KEYS = [
    (PromptAction.ACCEPT, "[enter accept]"),
    (PromptAction.SEARCH, "[s]earch"),
    (PromptAction.MANUAL, "[m]etadata"),
    (PromptAction.SKIP, "[x]skip"),
    (PromptAction.QUIT, "[q]uit"),
]


_EDIT_KEY = "[e]dit files"


def _render_action_keys(
    default: PromptAction | None, *, has_companions: bool = False
) -> Text:
    """Build a Rich Text line showing available actions.

    The default action is rendered bold; all others are dim.
    The ``[e]dit files`` key is only shown when companions are present.
    """
    line = Text()
    keys = list(_ACTION_KEYS)
    if has_companions:
        keys.append((None, _EDIT_KEY))
    for i, (action, label) in enumerate(keys):
        if i > 0:
            line.append("  ")
        if action is not None and action == default:
            line.append(label, style="bold")
        else:
            line.append(label, style="dim")
    return line


def _format_match(result: object) -> str:
    """Format a single match line: Title (Year)  tmdb:ID  confidence%."""
    title = getattr(result, "title", "???")
    year = getattr(result, "year", None)
    tmdb_id = getattr(result, "tmdb_id", "?")
    confidence = getattr(result, "confidence", 0.0)

    title_part = f"{title} ({year})" if year is not None else title
    conf_pct = f"{int(confidence * 100)}%"
    return f"{title_part}  tmdb:{tmdb_id}  {conf_pct}"


def display_prompt(
    console: Console,
    prompt: InteractivePrompt,
    *,
    index: int,
    total: int,
    filename: str,
    source: str | None = None,
    companions: list | None = None,
) -> None:
    """Render the interactive import prompt to a Rich Console.

    Shows a header with progress, match info, and action keys.
    """
    # Header: [N/total] filename
    header = Text()
    header.append(f"[{index}/{total}]", style="bold")
    header.append(f" {filename}")
    console.print(header)

    candidates = prompt.candidates

    if not candidates:
        line = Text("-> no match found", style="dim")
        console.print(line)
    elif len(candidates) == 1:
        match_str = _format_match(candidates[0])
        source_str = f"  [{source}]" if source else ""
        console.print(Text(f"-> {match_str}{source_str}"))
    else:
        for num, cand in enumerate(candidates, 1):
            match_str = _format_match(cand)
            source_str = f"  [{source}]" if source else ""
            console.print(Text(f"{num}. {match_str}{source_str}"))

    # Companion files
    has_companions = bool(companions)
    if has_companions:
        _render_companions(console, companions)

    # Action keys
    action_line = _render_action_keys(prompt.default_action, has_companions=has_companions)
    console.print(action_line)


# --- Companion file rendering ---

_CATEGORY_WIDTH = 12  # right-align category names to this width


def _render_companions(console: Console, companions: list[CompanionFile]) -> None:
    """Render companion files grouped by category."""
    for comp in companions:
        marker = "+" if comp.move_by_default else "?"
        cat_label = comp.category.value.rjust(_CATEGORY_WIDTH)
        line = Text()
        line.append(f"{cat_label}   {marker}  {comp.relative_to_video}")
        console.print(line)


# --- Single keypress reader ---


def _read_key() -> str:
    """Read a single keypress from stdin.

    Returns the character as a string. This is a separate function so that
    tests can mock it.
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


# --- Read user action from prompt ---

_KEY_TO_ACTION = {
    "s": PromptAction.SEARCH,
    "m": PromptAction.MANUAL,
    "x": PromptAction.SKIP,
    "q": PromptAction.QUIT,
}


def read_action(
    prompt: InteractivePrompt,
    *,
    has_companions: bool = False,
) -> PromptAction | tuple[PromptAction, int] | str:
    """Read a single keypress and map it to a PromptAction.

    Returns:
        PromptAction for simple actions (search, skip, quit, manual, accept).
        (PromptAction.ACCEPT, index) when the user picks a numbered candidate.
        The string ``"edit"`` when ``e`` is pressed and companions exist.
    """
    # Ambiguous means multiple candidates without a clear default accept
    is_ambiguous = (
        len(prompt.candidates) > 1
        and prompt.default_action != PromptAction.ACCEPT
    )
    num_candidates = len(prompt.candidates)

    while True:
        key = _read_key()

        # Enter -> default action (if one exists)
        if key in ("\r", "\n"):
            if prompt.default_action is not None:
                return prompt.default_action
            continue  # no default, retry

        # Simple letter keys
        if key in _KEY_TO_ACTION:
            return _KEY_TO_ACTION[key]

        # Accept-all: 'a' when candidates exist
        if key == "a" and num_candidates > 0:
            return PromptAction.ACCEPT_ALL

        # Numbered candidate selection (only when ambiguous)
        if key.isdigit() and is_ambiguous:
            idx = int(key)
            if 1 <= idx <= num_candidates:
                return (PromptAction.ACCEPT, idx - 1)
            continue  # out of range, retry

        # Edit companions
        if key == "e" and has_companions:
            return "edit"

        # Invalid key, loop again


# --- Companion file checklist editor ---


def edit_companions(
    console: Console, companions: list[CompanionFile]
) -> list[CompanionFile]:
    """Show a togglable checklist for companion files.

    Video files are locked (always selected). Other files start at their
    ``move_by_default`` state. The user types a number to toggle, Enter to
    confirm.

    Returns:
        List of companion files that the user selected for import.
    """
    selected = [comp.move_by_default or comp.category == Category.VIDEO for comp in companions]

    while True:
        # Render checklist
        for i, comp in enumerate(companions):
            is_video = comp.category == Category.VIDEO
            if is_video:
                mark = "x"
                lock = " (locked)"
            else:
                mark = "x" if selected[i] else " "
                lock = ""
            line = Text()
            line.append(f"  {i}  [{mark}]  {comp.category.value:>12}  {comp.relative_to_video}{lock}")
            console.print(line)

        console.print(Text("Toggle number, Enter to confirm: ", style="dim"), end="")

        key = _read_key()
        if key in ("\r", "\n"):
            break
        if key.isdigit():
            idx = int(key)
            if 0 <= idx < len(companions):
                # Video files cannot be toggled
                if companions[idx].category != Category.VIDEO:
                    selected[idx] = not selected[idx]

    return [comp for comp, sel in zip(companions, selected) if sel]
