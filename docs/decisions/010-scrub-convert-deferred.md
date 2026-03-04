# ADR-010: scrub and convert plugins deferred

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
The `scrub` (strip metadata tags from files) and `convert` (transcode via ffmpeg) plugins are not implemented in v0.1. They are explicitly planned for a future release.

## Why
Both plugins are thin wrappers around external tools (mutagen/ffmpeg) and add significant scope without being necessary for the core library organisation workflow. The plugin system via EventBus exists specifically so these can be added later without touching the core.

## Alternatives considered
- **Implement convert as core feature**: rejected — transcoding is a destructive, long-running operation that needs its own UX (progress, cancellation, quality settings). Too much for v0.1.
- **Cut entirely**: rejected — both are genuinely useful for a media library tool. Deferring, not cutting.

## Consequences
The `[convert]` and `[scrub]` config sections can appear in user configs without error (unknown sections are ignored unless they have a known plugin name). Plugin entry points for these are not registered until implemented.
