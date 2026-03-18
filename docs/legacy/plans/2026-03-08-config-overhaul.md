# Config Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate config from plain Pydantic BaseModel to pydantic-settings so every setting is available via CLI flag, env var, and YAML config file with clear precedence.

**Architecture:** `TapesConfig` becomes a pydantic-settings `BaseSettings` subclass. A `load_config()` factory resolves the YAML path (CLI flag > `TAPES_CONFIG` env > XDG default), loads YAML, merges env vars, and applies CLI overrides. Precedence: CLI > env > YAML > defaults. New `AdvancedConfig` group holds power-user tuning (max_workers, tmdb_timeout, tmdb_retries). Consumers (scanner, tmdb, pipeline, similarity) receive config values as function parameters instead of reading module-level constants.

**Tech Stack:** pydantic-settings[yaml], pydantic v2, typer (rich_help_panel), platformdirs (XDG paths)

**Design doc:** `docs/plans/2026-03-08-config-overhaul-design.md`

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add pydantic-settings and platformdirs to dependencies**

In `pyproject.toml`, add to the `dependencies` list:
```toml
"pydantic-settings[yaml]>=2.7,<3",
"platformdirs>=4,<5",
```

`pydantic-settings[yaml]` pulls in `pyyaml` transitively, so we can drop the
explicit `pyyaml` dependency. `platformdirs` provides cross-platform XDG path
resolution.

**Step 2: Sync and verify**

Run: `uv sync`
Expected: installs pydantic-settings, platformdirs. No conflicts.

Run: `uv run python -c "from pydantic_settings import BaseSettings; from platformdirs import user_config_dir; print('ok')"`
Expected: `ok`

**Step 3: Commit**

```
feat: add pydantic-settings and platformdirs dependencies
```

---

### Task 2: Migrate config.py to BaseSettings

This is the core migration. Convert `TapesConfig` from `BaseModel` to
`BaseSettings`, add env var support, add new fields, validate operation,
and wire up YAML loading with XDG default.

**Files:**
- Modify: `tapes/config.py`
- Test: `tests/test_config.py`

**Step 1: Write failing tests for BaseSettings behavior**

Add these tests to `tests/test_config.py`. They test env var loading via
pydantic-settings (replacing the manual `model_post_init` approach):

```python
class TestEnvVarLoading:
    """Test that pydantic-settings loads env vars with TAPES_ prefix."""

    def test_tmdb_token_via_prefixed_env(self, monkeypatch):
        monkeypatch.setenv("TAPES_METADATA__TMDB_TOKEN", "from-prefixed-env")
        monkeypatch.delenv("TMDB_TOKEN", raising=False)
        cfg = TapesConfig()
        assert cfg.metadata.tmdb_token == "from-prefixed-env"

    def test_dry_run_via_env(self, monkeypatch):
        monkeypatch.setenv("TAPES_DRY_RUN", "true")
        cfg = TapesConfig()
        assert cfg.dry_run is True

    def test_operation_via_env(self, monkeypatch):
        monkeypatch.setenv("TAPES_LIBRARY__OPERATION", "move")
        cfg = TapesConfig()
        assert cfg.library.operation == "move"

    def test_max_workers_via_env(self, monkeypatch):
        monkeypatch.setenv("TAPES_ADVANCED__MAX_WORKERS", "8")
        cfg = TapesConfig()
        assert cfg.advanced.max_workers == 8
```

Run: `uv run pytest tests/test_config.py::TestEnvVarLoading -v`
Expected: FAIL (no `BaseSettings`, no `AdvancedConfig`, no env loading)

**Step 2: Write failing tests for operation validation**

```python
class TestOperationValidation:
    def test_valid_operations(self):
        for op in ("copy", "move", "link", "hardlink"):
            cfg = LibraryConfig(operation=op)
            assert cfg.operation == op

    def test_invalid_operation_raises(self):
        with pytest.raises(ValidationError):
            LibraryConfig(operation="ftp")
```

Run: `uv run pytest tests/test_config.py::TestOperationValidation -v`
Expected: FAIL (`operation` is `str`, no validation)

**Step 3: Write failing tests for new config fields**

```python
class TestAdvancedConfig:
    def test_defaults(self):
        cfg = AdvancedConfig()
        assert cfg.max_workers == 4
        assert cfg.tmdb_timeout == 10.0
        assert cfg.tmdb_retries == 3

    def test_custom_values(self):
        cfg = AdvancedConfig(max_workers=8, tmdb_timeout=30.0, tmdb_retries=5)
        assert cfg.max_workers == 8


class TestNewMetadataFields:
    def test_margin_defaults(self):
        cfg = MetadataConfig()
        assert cfg.margin_accept_threshold == 0.6
        assert cfg.min_accept_margin == 0.15
        assert cfg.max_results == 3

    def test_custom_margin(self):
        cfg = MetadataConfig(margin_accept_threshold=0.7, min_accept_margin=0.2, max_results=5)
        assert cfg.margin_accept_threshold == 0.7


class TestNewScanFields:
    def test_video_extensions_default(self):
        cfg = ScanConfig()
        assert ".mkv" in cfg.video_extensions
        assert ".mp4" in cfg.video_extensions
        assert len(cfg.video_extensions) == 9

    def test_video_extensions_custom(self):
        cfg = ScanConfig(video_extensions=[".mkv", ".webm"])
        assert cfg.video_extensions == [".mkv", ".webm"]
```

Run: `uv run pytest tests/test_config.py::TestAdvancedConfig -v`
Expected: FAIL (no `AdvancedConfig`)

**Step 4: Write failing tests for TMDB_TOKEN backwards compat**

The legacy `TMDB_TOKEN` env var (without prefix) must keep working:

```python
class TestTmdbTokenCompat:
    def test_legacy_tmdb_token_env(self, monkeypatch):
        """TMDB_TOKEN (no prefix) still works for backwards compat."""
        monkeypatch.delenv("TAPES_METADATA__TMDB_TOKEN", raising=False)
        monkeypatch.setenv("TMDB_TOKEN", "legacy-token")
        cfg = TapesConfig()
        assert cfg.metadata.tmdb_token == "legacy-token"

    def test_prefixed_overrides_legacy(self, monkeypatch):
        """TAPES_METADATA__TMDB_TOKEN takes priority over TMDB_TOKEN."""
        monkeypatch.setenv("TAPES_METADATA__TMDB_TOKEN", "new-style")
        monkeypatch.setenv("TMDB_TOKEN", "old-style")
        cfg = TapesConfig()
        assert cfg.metadata.tmdb_token == "new-style"
```

Run: `uv run pytest tests/test_config.py::TestTmdbTokenCompat -v`
Expected: FAIL

**Step 5: Write failing tests for YAML config file loading**

```python
class TestYamlConfigSource:
    def test_load_from_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "library": {"movies": "/media/movies", "operation": "move"},
            "metadata": {"auto_accept_threshold": 0.7},
        }))
        cfg = load_config(config_path=config_file)
        assert cfg.library.movies == "/media/movies"
        assert cfg.library.operation == "move"
        assert cfg.metadata.auto_accept_threshold == 0.7

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"library": {"operation": "copy"}}))
        monkeypatch.setenv("TAPES_LIBRARY__OPERATION", "move")
        cfg = load_config(config_path=config_file)
        assert cfg.library.operation == "move"

    def test_cli_overrides_env_and_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"library": {"operation": "copy"}}))
        monkeypatch.setenv("TAPES_LIBRARY__OPERATION", "move")
        cfg = load_config(config_path=config_file, cli_overrides={"library": {"operation": "hardlink"}})
        assert cfg.library.operation == "hardlink"

    def test_missing_yaml_uses_defaults(self, tmp_path):
        cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
        assert cfg == TapesConfig()

    def test_empty_yaml_uses_defaults(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        cfg = load_config(config_path=config_file)
        assert cfg.library.operation == "copy"
```

Run: `uv run pytest tests/test_config.py::TestYamlConfigSource -v`
Expected: FAIL

**Step 6: Write failing test for XDG default path**

```python
def test_default_config_path(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/fake/config")
    assert default_config_path() == Path("/fake/config/tapes/config.yaml")

def test_config_path_from_env(monkeypatch):
    monkeypatch.setenv("TAPES_CONFIG", "/custom/tapes.yaml")
    assert resolve_config_path(None) == Path("/custom/tapes.yaml")

def test_config_path_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("TAPES_CONFIG", "/custom/tapes.yaml")
    assert resolve_config_path(Path("/explicit.yaml")) == Path("/explicit.yaml")
```

Run: `uv run pytest tests/test_config.py::test_default_config_path -v`
Expected: FAIL

**Step 7: Implement config.py**

Rewrite `tapes/config.py`:

- Import `BaseSettings`, `SettingsConfigDict` from `pydantic_settings`
- Import `YamlConfigSettingsSource` from `pydantic_settings`
- Import `user_config_dir` from `platformdirs`
- Keep sub-models (`ScanConfig`, `MetadataConfig`, `LibraryConfig`) as
  `BaseModel` (only the root needs `BaseSettings`)
- Add `AdvancedConfig(BaseModel)` with `max_workers: int = 4`,
  `tmdb_timeout: float = 10.0`, `tmdb_retries: int = 3`
- Add `video_extensions: list[str]` to `ScanConfig` with default from
  current `scanner.py VIDEO_EXTENSIONS`
- Add `margin_accept_threshold: float = 0.6`,
  `min_accept_margin: float = 0.15`, `max_results: int = 3` to
  `MetadataConfig`
- Change `operation: str = "copy"` to
  `operation: Literal["copy", "move", "link", "hardlink"] = "copy"`
- Make `TapesConfig` extend `BaseSettings` with:
  - `model_config = SettingsConfigDict(env_prefix="TAPES_", env_nested_delimiter="__")`
  - `advanced: AdvancedConfig = AdvancedConfig()` field
- Add `TMDB_TOKEN` backwards compat via `model_validator` (check legacy
  env var if `tmdb_token` is empty after settings resolution)
- Add `default_config_path() -> Path` using `platformdirs.user_config_dir`
- Add `resolve_config_path(explicit: Path | None) -> Path | None` that
  checks explicit arg > `TAPES_CONFIG` env > XDG default (only if file
  exists)
- Rewrite `load_config(config_path, cli_overrides)` to:
  1. Resolve YAML path
  2. If YAML exists, read it and parse as dict
  3. Merge: start with YAML data, let `TapesConfig(**cli_overrides)` handle
     env override via pydantic-settings

Implementation note on YAML + env + CLI layering: pydantic-settings
`BaseSettings` handles env automatically. For YAML + CLI, the cleanest
approach is:
- Override `settings_customise_sources()` to add `YamlConfigSettingsSource`
- Pass CLI overrides as `__init__` kwargs (highest priority in
  pydantic-settings by default)
- The `load_config()` function sets up the YAML path and constructs
  `TapesConfig` with the right sources

The YAML source needs a dynamic file path. Use `model_config` with
`yaml_file` set at construction time, or pass via `_yaml_file` init param
if pydantic-settings supports it. If not, create a thin wrapper that
subclasses or configures the source at call time.

**Step 8: Run all config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

Fix the existing tests that break due to the migration (e.g.,
`TestMetadataConfig` tests that relied on `model_post_init` behavior).
Update them to work with the new env var mechanism. The old
`test_tmdb_token_from_env` test should still pass -- `TMDB_TOKEN` still
works via the backwards compat validator.

**Step 9: Run full test suite**

Run: `uv run pytest`
Expected: PASS (no regressions). Some tests may need updating if they
create `TapesConfig()` and pydantic-settings picks up stray env vars.
Use `monkeypatch.delenv` to isolate those tests, or set
`model_config` with `env_ignore_empty = True`.

**Step 10: Commit**

```
feat: migrate config to pydantic-settings with env vars, YAML source, validation

- BaseModel -> BaseSettings with TAPES_ prefix and __ nested delimiter
- Add AdvancedConfig (max_workers, tmdb_timeout, tmdb_retries)
- Add video_extensions to ScanConfig, margin thresholds to MetadataConfig
- Validate operation as Literal["copy", "move", "link", "hardlink"]
- YAML config file loading via pydantic-settings YamlConfigSettingsSource
- XDG default config path via platformdirs
- TAPES_CONFIG env var for custom config file location
- load_config() with CLI override support
- Backwards compat: TMDB_TOKEN env var still works
```

---

### Task 3: CLI flags with override mechanism

Add typer flags for all config settings, grouped via `rich_help_panel`.
Build override dict from explicitly-provided flags.

**Files:**
- Modify: `tapes/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing tests for CLI flags**

```python
class TestImportFlags:
    def test_operation_flag_in_help(self):
        result = runner.invoke(app, ["import", "--help"])
        assert "--operation" in result.output

    def test_tmdb_token_flag_in_help(self):
        result = runner.invoke(app, ["import", "--help"])
        assert "--tmdb-token" in result.output

    def test_max_workers_flag_in_help(self):
        result = runner.invoke(app, ["import", "--help"])
        assert "--max-workers" in result.output

    def test_help_panels_present(self):
        result = runner.invoke(app, ["import", "--help"])
        assert "Library" in result.output
        assert "Metadata" in result.output
        assert "Advanced" in result.output
```

Run: `uv run pytest tests/test_cli.py::TestImportFlags -v`
Expected: FAIL (no flags yet)

**Step 2: Implement CLI flags**

Modify `import_cmd` in `tapes/cli.py`:

- Add all config options as typer `Option` params with `None` defaults
  (sentinel: `None` means "not provided by user")
- Group flags using `rich_help_panel`:
  - "Library": `--library-movies`, `--library-tv`, `--movie-template`,
    `--tv-template`, `--operation`
  - "Metadata": `--tmdb-token`, `--auto-accept-threshold`,
    `--margin-accept-threshold`, `--min-accept-margin`, `--max-results`
  - "Scan": `--ignore-patterns`, `--video-extensions`
  - "Advanced": `--max-workers`, `--tmdb-timeout`, `--tmdb-retries`
- After typer parses args, build a nested dict of only non-None values:
  ```python
  def _build_overrides(**kwargs) -> dict:
      """Build nested override dict from non-None CLI args."""
      overrides = {}
      mapping = {
          "library_movies": ("library", "movies"),
          "library_tv": ("library", "tv"),
          "movie_template": ("library", "movie_template"),
          "operation": ("library", "operation"),
          "tmdb_token": ("metadata", "tmdb_token"),
          "max_workers": ("advanced", "max_workers"),
          # ... etc
      }
      for key, (section, field) in mapping.items():
          if kwargs.get(key) is not None:
              overrides.setdefault(section, {})[field] = kwargs[key]
      # Top-level fields
      if kwargs.get("dry_run"):
          overrides["dry_run"] = True
      return overrides
  ```
- Call `load_config(config_path=config_file, cli_overrides=overrides)`
- Remove manual `cfg.dry_run = True` logic (now handled by overrides)
- Apply same changes to `tree_cmd`

For list-type options (`--ignore-patterns`, `--video-extensions`): use
`typer.Option(None, help="...", callback=parse_csv)` where `parse_csv`
splits comma-separated input. Or use repeated flags.

**Step 3: Run CLI tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 4: Run full test suite**

Run: `uv run pytest`
Expected: PASS

**Step 5: Commit**

```
feat: add CLI flags for all config settings with help panel grouping
```

---

### Task 4: Wire scanner to use config

Pass `video_extensions` from config to `scan()` instead of using the
hardcoded `VIDEO_EXTENSIONS` constant.

**Files:**
- Modify: `tapes/scanner.py`
- Modify: `tapes/cli.py` (pass config)
- Test: `tests/test_scanner.py`

**Step 1: Write failing test**

```python
def test_scan_custom_video_extensions(tmp_path):
    """Custom video_extensions changes which files count as video."""
    (tmp_path / "movie.mkv").write_text("v")
    (tmp_path / "movie.webm").write_text("v")
    (tmp_path / "sample.mkv").write_text("s")
    (tmp_path / "sample.webm").write_text("s")
    # With default extensions, .webm is not a video, so sample.webm is kept
    # (sample filtering only applies to video files)
    files = scan(tmp_path)
    names = {f.name for f in files}
    assert "sample.webm" in names  # not filtered: webm not in default extensions

    # With custom extensions including .webm, sample.webm IS filtered
    files2 = scan(tmp_path, video_extensions=[".mkv", ".webm"])
    names2 = {f.name for f in files2}
    assert "sample.webm" not in names2  # now filtered as video sample
```

Run: `uv run pytest tests/test_scanner.py::test_scan_custom_video_extensions -v`
Expected: FAIL (`scan` doesn't accept `video_extensions`)

**Step 2: Implement**

In `tapes/scanner.py`:
- Keep `VIDEO_EXTENSIONS` as the default value (for backwards compat of
  the `scan()` function signature)
- Add `video_extensions: frozenset[str] | None = None` param to `scan()`
- If provided, use it; otherwise fall back to `VIDEO_EXTENSIONS`
- Pass to `_is_video()` as a parameter

In `tapes/cli.py`:
- Pass `cfg.scan.video_extensions` to `scan()` in both `import_cmd` and
  `tree_cmd`:
  ```python
  files = scan(resolved, ignore_patterns=cfg.scan.ignore_patterns,
               video_extensions=cfg.scan.video_extensions)
  ```

**Step 3: Run tests**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: ALL PASS (new test + existing tests unchanged)

**Step 4: Commit**

```
feat: make video extensions configurable via scan config
```

---

### Task 5: Wire tmdb to use config

Pass timeout, retries, and max_results from config instead of using
module-level constants.

**Files:**
- Modify: `tapes/tmdb.py`
- Test: `tests/test_tmdb.py` (if exists, or add tests inline)

**Step 1: Write failing tests**

```python
def test_create_client_custom_timeout():
    """create_client respects custom timeout."""
    client = create_client("fake-token", timeout=30.0)
    assert client._transport  # client created successfully
    client.close()

def test_search_multi_respects_max_results(respx_mock):
    """search_multi returns at most max_results items."""
    # Mock TMDB returning 5 results
    respx_mock.get("/search/multi").mock(return_value=httpx.Response(200, json={
        "results": [
            {"id": i, "media_type": "movie", "title": f"Movie {i}", "release_date": "2024-01-01"}
            for i in range(5)
        ]
    }))
    results = search_multi("test", "token", client=..., max_results=2)
    assert len(results) == 2
```

Run: `uv run pytest tests/test_tmdb.py -v` (or wherever tmdb tests live)
Expected: FAIL (functions don't accept these params yet)

**Step 2: Implement**

In `tapes/tmdb.py`:
- `create_client(token, timeout=REQUEST_TIMEOUT_S)` -- add `timeout` param
- `search_multi(..., max_results=MAX_TMDB_RESULTS)` -- add param, use
  instead of module constant
- `_request(..., max_retries=3)` -- remove `@tenacity.retry` decorator,
  use `tenacity.Retrying` context manager inside the function body with
  configurable `stop_after_attempt(max_retries)`:
  ```python
  def _request(method, path, token, client=None, max_retries=3, **kwargs):
      retryer = tenacity.Retrying(
          retry=tenacity.retry_if_exception(_is_retryable),
          wait=_retry_after_wait,
          stop=tenacity.stop_after_attempt(max_retries),
          reraise=True,
      )
      for attempt in retryer:
          with attempt:
              if client is not None:
                  resp = client.request(method, path, **kwargs)
                  resp.raise_for_status()
                  return resp
              with create_client(token) as c:
                  resp = c.request(method, path, **kwargs)
                  resp.raise_for_status()
                  return resp
  ```
- Keep `REQUEST_TIMEOUT_S`, `MAX_TMDB_RESULTS` as default values for
  backwards compat of function signatures. They are no longer authoritative
  -- config values override them.

**Step 3: Run tests**

Run: `uv run pytest tests/ -k tmdb -v`
Expected: ALL PASS

**Step 4: Commit**

```
feat: make tmdb timeout, retries, and max_results configurable
```

---

### Task 6: Wire pipeline to use config

Pass config values through the pipeline instead of importing
`DEFAULT_AUTO_ACCEPT_THRESHOLD` and `DEFAULT_MAX_WORKERS` as fallbacks.
Thread `max_results` and `max_retries` to tmdb calls.

**Files:**
- Modify: `tapes/pipeline.py`
- Modify: `tapes/ui/tree_app.py` (pass new config values)
- Test: `tests/test_ui/test_pipeline.py`

**Step 1: Write failing test**

```python
def test_run_tmdb_pass_custom_max_results(model_with_files, respx_mock):
    """max_results param is forwarded to TMDB searches."""
    # ... setup mock that returns 5 results ...
    run_tmdb_pass(model, token="t", max_results=1)
    # verify only 1 source per file
```

The exact test depends on the existing test patterns in
`tests/test_ui/test_pipeline.py`. Match the existing style.

Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: FAIL (`run_tmdb_pass` doesn't accept `max_results`)

**Step 2: Implement pipeline changes**

In `tapes/pipeline.py`:
- `run_tmdb_pass()`: add `max_results`, `tmdb_timeout`, `tmdb_retries`
  params with defaults from the module constants (which now match config
  defaults). Remove the `from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD`
  fallback pattern -- callers must provide `confidence_threshold`.
  Actually, keep the default for backwards compat of the function API, but
  prefer explicit passing.
- `refresh_tmdb_source()`: same new params
- `_query_tmdb_for_node()`: accept and forward `max_results`
- `_query_episodes()`: accept and forward `max_results`
- `create_client` calls: pass `timeout`
- `_request` calls (via tmdb functions): pass `max_retries`

In `tapes/ui/tree_app.py`:
- `_run_tmdb_worker()`: pass `max_workers`, `max_results`, `tmdb_timeout`,
  `tmdb_retries` from `self.config.advanced` and `self.config.metadata`
- `action_refresh_query()`: pass `max_results` from config
- Pass margin thresholds when calling `should_auto_accept` (currently
  these flow through `should_auto_accept`'s default params -- the
  pipeline should pass them explicitly from config)

**Step 3: Verify no references to removed constants**

Check that `DEFAULT_AUTO_ACCEPT_THRESHOLD` is no longer imported in
`pipeline.py` or `similarity.py` (the values now come from config or
function params). The constant can stay in `config.py` as the default
value for the `MetadataConfig.auto_accept_threshold` field.

Run: `uv run pytest`
Expected: ALL PASS

**Step 4: Commit**

```
feat: thread config values through pipeline to tmdb and similarity
```

---

### Task 7: Clean up and final verification

Remove dead constants, update docs, verify everything works end to end.

**Files:**
- Modify: `tapes/config.py` (remove `DEFAULT_AUTO_ACCEPT_THRESHOLD` export if unused)
- Modify: `tapes/scanner.py` (verify `VIDEO_EXTENSIONS` only used as default)
- Modify: `tapes/tmdb.py` (verify constants only used as defaults)
- Modify: `tapes/pipeline.py` (verify no stale imports)
- Modify: `tapes/similarity.py` (verify `MARGIN_ACCEPT_THRESHOLD`, `MIN_ACCEPT_MARGIN` only used as defaults)
- Modify: `docs/issues.md` (mark I29 as done)

**Step 1: Audit constant usage**

Grep for `DEFAULT_AUTO_ACCEPT_THRESHOLD`, `DEFAULT_MAX_WORKERS`,
`REQUEST_TIMEOUT_S`, `MAX_TMDB_RESULTS`, `VIDEO_EXTENSIONS`,
`MARGIN_ACCEPT_THRESHOLD`, `MIN_ACCEPT_MARGIN` across the codebase.

Each should only appear:
- In its defining module as a default value
- In tests that import it for assertions

Remove any stale imports elsewhere.

**Step 2: Run full test suite + linting**

Run: `uv run pytest`
Expected: ALL PASS

Run: `uv tool run ruff check tapes/ tests/`
Expected: clean

Run: `uv tool run ty check`
Expected: clean (or only pre-existing issues)

**Step 3: Update issues.md**

Mark I29 as done. Remove it from the "Defer" tier. Update the description
to reflect what was implemented.

**Step 4: Commit**

```
chore: clean up dead config constants, mark I29 done
```
