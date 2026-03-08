# Web UI (textual-serve + Docker) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Serve the tapes TUI over the browser via textual-serve, packaged as a Docker container.

**Architecture:** `tapes serve` command uses `textual_serve.server.Server` to spawn `tapes import` as a subprocess per browser connection. The subprocess inherits environment variables and config file, so all existing config mechanisms work unchanged. Docker container runs `tapes serve` with bind-mounted media directories.

**Tech Stack:** textual-serve (aiohttp + xterm.js), Docker, existing tapes core

---

### Task 1: Add `import_path` to ScanConfig

**Files:**
- Modify: `tapes/config.py:16-18`
- Modify: `config.example.yaml:50-57`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`, inside `TestScanConfig`:

```python
def test_import_path_default_empty(self) -> None:
    cfg = ScanConfig()
    assert cfg.import_path == ""

def test_import_path_custom(self) -> None:
    cfg = ScanConfig(import_path="/media/incoming")
    assert cfg.import_path == "/media/incoming"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::TestScanConfig::test_import_path_default_empty -v`
Expected: FAIL with `TypeError` (unexpected keyword)

**Step 3: Write minimal implementation**

In `tapes/config.py`, add to `ScanConfig`:

```python
class ScanConfig(BaseModel):
    import_path: str = ""
    ignore_patterns: list[str] = ["Thumbs.db", ".DS_Store", "desktop.ini"]
    video_extensions: list[str] = [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"]
```

In `config.example.yaml`, add under the `scan:` section:

```yaml
  # Default import directory (used by `tapes serve`).
  # import_path: /media/incoming
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py::TestScanConfig -v`
Expected: PASS (all 5 tests)

**Step 5: Add env var test**

Add to `tests/test_config.py`, inside `TestEnvVarLoading`:

```python
def test_import_path_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPES_SCAN__IMPORT_PATH", "/incoming")
    cfg = TapesConfig()
    assert cfg.scan.import_path == "/incoming"
```

Run: `uv run pytest tests/test_config.py::TestEnvVarLoading::test_import_path_via_env -v`
Expected: PASS (env var loading already works via pydantic-settings)

**Step 6: Commit**

```bash
git add tapes/config.py config.example.yaml tests/test_config.py
git commit -m "feat: add import_path to ScanConfig"
```

---

### Task 2: Make `tapes import` path argument optional

**Files:**
- Modify: `tapes/cli.py:87-88`
- Test: `tests/test_cli.py`

The path argument should fall back to `cfg.scan.import_path` when not provided. Error if neither is set.

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
class TestImportPathFallback:
    def test_import_uses_config_import_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """import_cmd uses scan.import_path from config when no path argument given."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        monkeypatch.setenv("TAPES_SCAN__IMPORT_PATH", str(scan_dir))

        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            result = runner.invoke(app, ["import"])
            assert result.exit_code == 0
            mock_app_cls.assert_called_once()

    def test_import_errors_when_no_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """import_cmd exits with error when no path argument and no import_path configured."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        result = runner.invoke(app, ["import"])
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestImportPathFallback -v`
Expected: FAIL (typer requires the path argument)

**Step 3: Implement**

In `tapes/cli.py`, change `import_cmd`:

```python
@app.command("import")
def import_cmd(
    path: Path | None = typer.Argument(None, help="Directory or file to import"),
    ...
) -> None:
    """Import video files into the library."""
    overrides = _build_overrides(...)
    cfg = load_config(config_path=config_file, cli_overrides=overrides)

    # Resolve import path: CLI argument > config
    if path is not None:
        resolved = path.resolve()
    elif cfg.scan.import_path:
        resolved = Path(cfg.scan.import_path).resolve()
    else:
        console.print("[red]Error:[/red] No path provided. Pass a directory or set scan.import_path in config.")
        raise typer.Exit(code=1)

    from tapes.scanner import scan
    ...
```

Note: the `overrides` dict must be built and `load_config` called BEFORE resolving the path, since the path may come from config. Move `cfg = load_config(...)` above the path resolution.

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py::TestImportPathFallback -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/cli.py tests/test_cli.py
git commit -m "feat: make import path argument optional, fall back to config"
```

---

### Task 3: Remove `tapes tree` command

**Files:**
- Modify: `tapes/cli.py:187-287` (remove `tree_cmd` function)
- Modify: `tests/test_cli.py` (remove tree tests)

**Step 1: Remove the command**

Delete the entire `tree_cmd` function from `tapes/cli.py` (lines 187-287).

**Step 2: Remove tree tests**

In `tests/test_cli.py`, delete:
- `test_tree_help()` function
- `TestTreeFlags` class (all methods)

**Step 3: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all remaining tests)

**Step 4: Commit**

```bash
git add tapes/cli.py tests/test_cli.py
git commit -m "refactor: remove tapes tree command"
```

---

### Task 4: Add `textual-serve` dependency

**Files:**
- Modify: `pyproject.toml:5-16`

**Step 1: Add dependency**

In `pyproject.toml`, add to the `dependencies` list:

```toml
"textual-serve>=1.1,<2",
```

**Step 2: Sync**

Run: `uv sync`

**Step 3: Verify import works**

Run: `uv run python -c "from textual_serve.server import Server; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add textual-serve"
```

---

### Task 5: Add `tapes serve` command

**Files:**
- Modify: `tapes/cli.py`
- Test: `tests/test_cli.py`

The serve command constructs a `tapes import <path>` command string and passes it to `textual_serve.server.Server`. The subprocess inherits all environment variables, so `TAPES_*` config works automatically. The serve command only needs `--host`, `--port`, and `--import-path` flags, plus the standard `--config` flag.

**Step 1: Write tests**

Add to `tests/test_cli.py`:

```python
def test_serve_help():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--import-path" in result.output


class TestServeCommand:
    def test_serve_errors_when_no_import_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        result = runner.invoke(app, ["serve"])
        assert result.exit_code != 0

    def test_serve_constructs_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        from unittest.mock import patch

        with patch("tapes.cli._start_server") as mock_start:
            runner.invoke(app, ["serve", "--import-path", "/media/incoming"])
            mock_start.assert_called_once()
            cmd, host, port = mock_start.call_args[0]
            assert "/media/incoming" in cmd
            assert host == "0.0.0.0"
            assert port == 8080
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_serve_help -v`
Expected: FAIL (command doesn't exist)

**Step 3: Implement**

Add to `tapes/cli.py`:

```python
def _start_server(command: str, host: str, port: int) -> None:
    """Start the textual-serve server. Extracted for testability."""
    from textual_serve.server import Server

    server = Server(command, host=host, port=port, title="tapes")
    server.serve()


@app.command("serve")
def serve_cmd(
    import_path: Path | None = typer.Option(None, "--import-path", help="Directory to import"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address"),
    port: int = typer.Option(8080, "--port", help="Port number"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Serve the tapes TUI over the browser."""
    import shlex

    cfg = load_config(config_path=config_file)

    # Resolve import path: --import-path flag > config
    resolved_path = import_path or (Path(cfg.scan.import_path) if cfg.scan.import_path else None)
    if resolved_path is None:
        console.print("[red]Error:[/red] No import path. Use --import-path or set TAPES_SCAN__IMPORT_PATH.")
        raise typer.Exit(code=1)

    cmd = f"tapes import {shlex.quote(str(resolved_path))}"
    if config_file:
        cmd += f" --config {shlex.quote(str(config_file))}"

    console.print(f"Serving tapes on http://{host}:{port}")
    _start_server(cmd, host, port)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/cli.py tests/test_cli.py
git commit -m "feat: add tapes serve command"
```

---

### Task 6: Dockerfile and docker-compose.yaml

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yaml`

**Step 1: Create Dockerfile**

```dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD ["uv", "run", "tapes", "serve"]
```

**Step 2: Create docker-compose.yaml**

```yaml
services:
  tapes:
    build: .
    ports:
      - "8080:8080"
    environment:
      - TAPES_SCAN__IMPORT_PATH=/import
      - TAPES_METADATA__TMDB_TOKEN=${TMDB_TOKEN:-}
      - TAPES_LIBRARY__MOVIES=/library/movies
      - TAPES_LIBRARY__TV=/library/tv
      # - TAPES_LIBRARY__OPERATION=copy
      # - TAPES_DRY_RUN=true
    volumes:
      - /path/to/downloads:/import:ro
      - /path/to/library:/library
      # Optional: mount config file
      # - ./config.yaml:/config/config.yaml
```

**Step 3: Verify Dockerfile builds**

Run: `docker build -t tapes .`
Expected: Successful build

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yaml
git commit -m "feat: add Dockerfile and docker-compose.yaml"
```

---

### Task 7: Add .dockerignore

**Files:**
- Create: `.dockerignore`

**Step 1: Create .dockerignore**

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.ruff_cache
.claude
docs/legacy
docs/mockups
tests
.worktrees
worktrees
```

**Step 2: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore"
```

---

### Task 8: Update docs and config example

**Files:**
- Modify: `config.example.yaml`
- Modify: `docs/issues.md` (if web UI was tracked there)

**Step 1: Update config.example.yaml**

Ensure the scan section has `import_path` documented (done in Task 1).

**Step 2: Commit**

```bash
git add config.example.yaml
git commit -m "docs: update config example with import_path"
```
