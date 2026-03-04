# ADR-004: OpenSubtitles API lookup deferred to post-v0.1

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
The OpenSubtitles movie hash is computed and available in the pipeline, but the API call to look up the hash is not implemented in v0.1. The hash is stored for future use.

## Why
The `opensubtitlescom` Python library (last commit Jan 2024) is the obvious client, but adding an API dependency with its own auth flow, rate limits, and reliability concerns is scope that isn't needed to ship a useful v0.1. TMDB identification handles the vast majority of cases.

## Alternatives considered
- **Implement now**: would improve identification accuracy for obscure files, but adds complexity and an external dependency before the core workflow is proven.
- **Drop the hash entirely**: rejected — computing the hash is cheap, and keeping it means we can add the API lookup later without a schema migration.

## Consequences
Hash is computed during identification but not used for lookup yet. When we add the API call, it slots into the pipeline at step 5 with no schema changes needed.
