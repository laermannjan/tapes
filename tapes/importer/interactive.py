"""Interactive prompt logic and default-action determination.

Determines what the default action should be when presenting identification
results to the user during interactive import mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from rich.console import Console
from rich.text import Text

logger = logging.getLogger(__name__)

STRONG_CONFIDENCE = 0.75
GAP_THRESHOLD = 0.2
_EPS = 1e-9  # tolerance for floating-point comparisons


class PromptAction(str, Enum):
    """Actions available at an interactive import prompt."""

    ACCEPT = "accept"
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


def _render_action_keys(default: PromptAction | None) -> Text:
    """Build a Rich Text line showing available actions.

    The default action is rendered bold; all others are dim.
    """
    line = Text()
    for i, (action, label) in enumerate(_ACTION_KEYS):
        if i > 0:
            line.append("  ")
        if action == default:
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

    # Action keys
    action_line = _render_action_keys(prompt.default_action)
    console.print(action_line)
