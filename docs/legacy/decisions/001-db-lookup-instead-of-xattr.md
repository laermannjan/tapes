# ADR-001: DB lookup instead of xattr for file identity cache

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
Use DB lookup by (path, mtime, size) to detect already-known files on re-import instead of storing metadata in extended file attributes (xattr).

## Why
xattr is not available on Windows, which is a primary target platform. The DB lookup covers the same use case without any platform-specific dependency, and we have a DB already.

## Alternatives considered
- **xattr**: fast, no DB round-trip, survives file moves if path changes. Rejected: no Windows support, adds a platform dependency for marginal gain.

## Consequences
All caching goes through the DB. Files must have been previously imported to benefit. First-time scans always run the full identification pipeline.
