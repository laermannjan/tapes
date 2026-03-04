# ADR-007: uv for package management

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
Use `uv` for virtual environment management, dependency installation, and running tests/scripts. The project uses `[dependency-groups]` in `pyproject.toml` (the uv convention) rather than `[project.optional-dependencies]`.

## Why
uv is significantly faster than pip/venv for installs, has a built-in lockfile, and is the direction the Python packaging ecosystem is moving. It was already installed in the development environment.

## Alternatives considered
- **pip + venv**: works everywhere, no extra tooling. Rejected: slower, no lockfile, more manual workflow.
- **Poetry**: mature, good lockfile. Rejected: uv is faster and simpler for a project of this size.
- **Hatch**: pairs naturally with hatchling (our build backend). Considered, but uv works equally well with hatchling and is faster.

## Consequences
Contributors need uv installed. `uv sync` sets up the environment. `uv run pytest` runs tests. The build backend remains hatchling — uv is the workflow tool, not the build tool.
