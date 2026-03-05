from unittest.mock import MagicMock, patch

import pytest

from tapes.plugins.loader import PluginError, load_plugins


class FakePlugin:
    name = "fake"

    def setup(self, config, event_bus):
        self.config = config
        self.event_bus = event_bus


class FakePluginWithTeardown:
    name = "fake"

    def setup(self, config, event_bus):
        self.config = config
        self.event_bus = event_bus

    def teardown(self):
        pass


class FakePluginNoSetup:
    name = "broken"


def _make_ep(name, cls):
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = cls
    return ep


class TestLoadPlugins:
    def test_loads_enabled_plugin(self):
        """Plugin with matching config section and enabled=True is loaded."""
        ep = _make_ep("fake", FakePlugin)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            bus = MagicMock()
            plugins = load_plugins(
                {"fake": {"enabled": True, "option1": "value"}}, bus
            )

        assert len(plugins) == 1
        assert plugins[0].name == "fake"
        assert plugins[0].config == {"enabled": True, "option1": "value"}
        assert plugins[0].event_bus is bus

    def test_skips_disabled_plugin(self):
        """Plugin with enabled=False is not loaded."""
        ep = _make_ep("fake", FakePlugin)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            plugins = load_plugins({"fake": {"enabled": False}}, MagicMock())

        assert len(plugins) == 0

    def test_skips_plugin_not_in_config(self):
        """Plugin with no config section is not loaded."""
        ep = _make_ep("fake", FakePlugin)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            plugins = load_plugins({}, MagicMock())

        assert len(plugins) == 0

    def test_empty_entry_points(self):
        """No entry points discovered returns empty list."""
        with patch("tapes.plugins.loader._discover_entry_points", return_value=[]):
            plugins = load_plugins({"fake": {"enabled": True}}, MagicMock())

        assert len(plugins) == 0

    def test_plugin_setup_error_raises(self):
        """Plugin that raises in setup produces PluginError."""

        class BadPlugin:
            name = "bad"

            def setup(self, config, event_bus):
                raise RuntimeError("boom")

        ep = _make_ep("bad", BadPlugin)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            with pytest.raises(PluginError, match="bad"):
                load_plugins({"bad": {"enabled": True}}, MagicMock())

    def test_known_keys_ignored(self):
        """Known non-plugin keys are never treated as plugin config."""
        ep = _make_ep("library", FakePlugin)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            plugins = load_plugins({"library": {"movies": "/tmp"}}, MagicMock())

        assert len(plugins) == 0

    def test_all_known_keys_ignored(self):
        """All known non-plugin keys are skipped."""
        known = ["library", "import", "metadata", "templates", "replace", "companions"]
        eps = [_make_ep(name, FakePlugin) for name in known]

        config = {name: {"enabled": True} for name in known}
        with patch("tapes.plugins.loader._discover_entry_points", return_value=eps):
            plugins = load_plugins(config, MagicMock())

        assert len(plugins) == 0

    def test_multiple_plugins_loaded(self):
        """Multiple enabled plugins are all loaded."""

        class PluginA:
            name = "alpha"

            def setup(self, config, event_bus):
                self.config = config

        class PluginB:
            name = "beta"

            def setup(self, config, event_bus):
                self.config = config

        eps = [_make_ep("alpha", PluginA), _make_ep("beta", PluginB)]

        with patch("tapes.plugins.loader._discover_entry_points", return_value=eps):
            plugins = load_plugins(
                {"alpha": {"enabled": True}, "beta": {"enabled": True}},
                MagicMock(),
            )

        assert len(plugins) == 2
        names = {p.name for p in plugins}
        assert names == {"alpha", "beta"}

    def test_plugin_with_teardown(self):
        """Plugin with optional teardown method is loaded normally."""
        ep = _make_ep("fake", FakePluginWithTeardown)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            plugins = load_plugins({"fake": {"enabled": True}}, MagicMock())

        assert len(plugins) == 1
        assert hasattr(plugins[0], "teardown")

    def test_enabled_defaults_to_false(self):
        """Config section without enabled key is treated as disabled."""
        ep = _make_ep("fake", FakePlugin)

        with patch("tapes.plugins.loader._discover_entry_points", return_value=[ep]):
            plugins = load_plugins({"fake": {"option1": "value"}}, MagicMock())

        assert len(plugins) == 0
