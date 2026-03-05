"""Plugin discovery and loading via entry points."""

import importlib.metadata
import logging

logger = logging.getLogger(__name__)

KNOWN_KEYS = frozenset(
    {"library", "import", "metadata", "templates", "replace", "companions"}
)


class PluginError(Exception):
    """Raised when a plugin fails to load or initialize."""


def _discover_entry_points():
    """Return all entry points in the 'tapes.plugins' group."""
    return list(importlib.metadata.entry_points(group="tapes.plugins"))


def load_plugins(plugin_config: dict, event_bus) -> list:
    """Discover and load plugins that are enabled in the config.

    Args:
        plugin_config: Top-level config dict. Plugin sections are identified
            by name (matching entry point name) and must have ``enabled = true``.
            Known non-plugin keys (library, import, etc.) are ignored.
        event_bus: The EventBus instance passed to each plugin's ``setup()``.

    Returns:
        List of instantiated and configured plugin objects.

    Raises:
        PluginError: If a plugin's ``setup()`` method raises an exception.
    """
    entry_points = _discover_entry_points()
    loaded = []

    for ep in entry_points:
        if ep.name in KNOWN_KEYS:
            continue

        section = plugin_config.get(ep.name)
        if not section or not section.get("enabled", False):
            continue

        plugin_cls = ep.load()
        plugin = plugin_cls()
        try:
            plugin.setup(section, event_bus)
        except Exception as e:
            raise PluginError(
                f"Plugin '{ep.name}' failed to setup: {e}"
            ) from e

        loaded.append(plugin)
        logger.info("Loaded plugin: %s", ep.name)

    return loaded
