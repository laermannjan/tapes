"""Shared test helpers for UI widget tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch


def render_plain(widget, width: int = 80, height: int = 20) -> str:
    """Render a widget and return its plain text content.

    Patches the widget's ``size`` property so rendering works outside a
    live Textual application.
    """
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)):
        rendered = widget.render()
    return rendered.plain
