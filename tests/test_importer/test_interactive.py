"""Tests for interactive prompt logic and default-action determination."""

from unittest.mock import MagicMock

from tapes.importer.interactive import InteractivePrompt, PromptAction


def _candidate(confidence):
    c = MagicMock()
    c.confidence = confidence
    return c


# --- Default action tests based on design doc table ---


def test_accept_on_enter_high_confidence():
    prompt = InteractivePrompt(candidates=[_candidate(0.86)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_accept_when_gap_large():
    """Single strong match with big gap to #2."""
    prompt = InteractivePrompt(candidates=[_candidate(0.70), _candidate(0.45)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_search_on_enter_low_confidence():
    """Single match below 0.75 with no big gap."""
    prompt = InteractivePrompt(candidates=[_candidate(0.55)])
    assert prompt.default_action == PromptAction.SEARCH


def test_search_on_enter_ambiguous():
    """Multiple candidates close together."""
    prompt = InteractivePrompt(candidates=[_candidate(0.65), _candidate(0.60)])
    assert prompt.default_action == PromptAction.SEARCH


def test_search_on_enter_no_match():
    prompt = InteractivePrompt(candidates=[])
    assert prompt.default_action == PromptAction.SEARCH


def test_skip_on_enter_after_failed_search():
    prompt = InteractivePrompt(candidates=[], after_failed_search=True)
    assert prompt.default_action == PromptAction.SKIP


def test_search_results_dominant():
    """After search, one result dominates."""
    prompt = InteractivePrompt(
        candidates=[_candidate(0.90), _candidate(0.65)],
        is_search_result=True,
    )
    assert prompt.default_action == PromptAction.ACCEPT


def test_search_results_close():
    """After search, results too close - no default."""
    prompt = InteractivePrompt(
        candidates=[_candidate(0.70), _candidate(0.60)],
        is_search_result=True,
    )
    assert prompt.default_action is None


# --- Edge cases ---


def test_accept_at_exact_threshold():
    """Confidence exactly at STRONG_CONFIDENCE threshold."""
    prompt = InteractivePrompt(candidates=[_candidate(0.75)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_accept_gap_exactly_at_threshold():
    """Gap exactly at GAP_THRESHOLD."""
    prompt = InteractivePrompt(candidates=[_candidate(0.60), _candidate(0.40)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_search_gap_just_below_threshold():
    """Gap just below GAP_THRESHOLD, confidence below strong."""
    prompt = InteractivePrompt(candidates=[_candidate(0.60), _candidate(0.41)])
    assert prompt.default_action == PromptAction.SEARCH


def test_search_results_single_candidate():
    """Search results with only one candidate - gap to 0 is the confidence itself."""
    prompt = InteractivePrompt(
        candidates=[_candidate(0.50)],
        is_search_result=True,
    )
    assert prompt.default_action == PromptAction.ACCEPT


def test_prompt_action_values():
    """PromptAction enum has expected string values."""
    assert PromptAction.ACCEPT == "accept"
    assert PromptAction.SEARCH == "search"
    assert PromptAction.SKIP == "skip"
    assert PromptAction.MANUAL == "manual"
    assert PromptAction.QUIT == "quit"


# --- display_prompt tests ---

import re
from io import StringIO
from rich.console import Console
from tapes.importer.interactive import display_prompt
from tapes.metadata.base import SearchResult

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _search_result(title="Dune", year=2021, tmdb_id=438631, confidence=0.94,
                   media_type="movie", **kwargs):
    return SearchResult(
        tmdb_id=tmdb_id, title=title, year=year,
        media_type=media_type, confidence=confidence, **kwargs,
    )


def test_display_single_match_shows_title_and_confidence():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=5, filename="Dune.2021.2160p.BluRay.mkv",
                   source="filename")
    output = _strip_ansi(buf.getvalue())
    assert "Dune (2021)" in output
    assert "tmdb:438631" in output
    assert "94%" in output
    assert "[1/5]" in output
    assert "filename" in output


def test_display_accept_is_default_for_strong_match():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result(confidence=0.86)])
    display_prompt(con, prompt, index=2, total=8, filename="Dune.2021.mkv",
                   source="filename")
    output = _strip_ansi(buf.getvalue())
    assert "accept" in output.lower()


def test_display_no_match():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[])
    display_prompt(con, prompt, index=3, total=10, filename="unknown_file.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "no match found" in output.lower()


def test_display_multiple_candidates_numbered():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    candidates = [
        _search_result(title="Blade Runner", year=1982, tmdb_id=78, confidence=0.62),
        _search_result(title="Blade Runner 2049", year=2017, tmdb_id=335984, confidence=0.55),
    ]
    prompt = InteractivePrompt(candidates=candidates)
    display_prompt(con, prompt, index=1, total=3, filename="Blade.Runner.mkv",
                   source="filename")
    output = _strip_ansi(buf.getvalue())
    assert "1." in output
    assert "2." in output
    assert "Blade Runner (1982)" in output
    assert "Blade Runner 2049 (2017)" in output


def test_display_no_source_omits_bracket():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=1, filename="Dune.mkv")
    output = _strip_ansi(buf.getvalue())
    # source brackets should not appear when source is None
    assert "[filename]" not in output


def test_display_action_keys_shown():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=1, filename="Dune.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "[s]earch" in output.lower()
    assert "[x]skip" in output.lower()
    assert "[q]uit" in output.lower()


def test_display_skip_is_default_after_failed_search():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[], after_failed_search=True)
    display_prompt(con, prompt, index=1, total=1, filename="mystery.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "skip" in output.lower()


def test_display_year_none():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result(year=None)])
    display_prompt(con, prompt, index=1, total=1, filename="Dune.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "Dune" in output
    # Should not show "(None)"
    assert "(None)" not in output
