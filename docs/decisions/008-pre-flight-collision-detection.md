# ADR-008: Pre-flight collision detection before any file operation

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
Before any file is moved or copied, tapes computes all destination paths and checks for collisions. Two types are distinguished:

- **Type A (template-only):** two different files map to the same destination because the template doesn't include a differentiating field (e.g. two editions of the same film). Resolution: offer to add a disambiguating field to the destination path, once, for this operation only.
- **Type B (likely duplicate):** two files share all significant metadata and differ only in technical details (codec, resolution). Resolution: offer to keep the higher-quality file, keep both with a suffix, or skip.

## Why
beets handles collisions passively with `%aunique`/`%sunique` template functions that append disambiguators automatically. We want the user to make an explicit decision rather than silently producing `Film (2021) 2.mkv`. For a library organiser, silent disambiguation is worse than a prompt.

## Alternatives considered
- **beets-style passive disambiguation**: appends a suffix automatically. Rejected: hides the collision from the user, can produce confusing filenames.
- **Abort on collision**: safe but requires the user to re-run after fixing each conflict manually.
- **Post-hoc detection**: detect after files are written. Rejected: too late, damage is done.

## Consequences
Pre-flight adds a pass over all planned destinations before the first file is touched. For large imports this is fast (no I/O, just path comparison). Collision resolution is one-time and ad-hoc — it does not modify the configured template.
