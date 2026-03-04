# ADR-009: Multi-episode files are manual-only in v0.1

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
When guessit detects a multi-episode file (e.g. `S01E01E02.mkv`), it returns a list of episode numbers. In v0.1, auto-detection of this case is not supported. The user must enter metadata manually using the `s01e01-e02` syntax in the interactive prompt. tapes produces the `S01E01E02` filename convention.

## Why
guessit returns `episode: [1, 2]` for multi-episode files. The rest of the pipeline assumes a single integer. Handling the list correctly throughout the template engine, DB schema, and TMDB queries adds non-trivial complexity. Multi-episode files are uncommon enough that manual entry is an acceptable workaround for v0.1.

## Alternatives considered
- **Auto-detect and handle**: correct long-term solution, deferred to v0.2.
- **Reject multi-episode files**: too aggressive — users would have no path forward.

## Consequences
The identification pipeline must guard against a list value for `episode` and route to manual entry when detected. The DB `episode` column stores a single integer — multi-episode representation in the filename only.
