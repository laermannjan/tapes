# ADR-005: No interactive undo — session log is the audit trail

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
There is no `tapes undo` command. The session log (`tapes log`) shows every operation that ran. Users who made a wrong import must reverse it manually.

## Why
Reliable undo is hard: it requires reversing file operations that may have already been moved, re-importing to original paths, handling partial sessions, and dealing with files that have since been modified. The engineering cost is high relative to how often it's needed, especially given the other safety measures in place (confidence threshold, dry-run, source-intact-until-DB-written).

## Alternatives considered
- **Full undo**: too complex for v0.1, and the blast radius is already limited by keeping the source file intact until the DB record is written.
- **Undo for copy mode only**: simpler since originals are intact, but still requires re-implementing the reverse pipeline.

## Consequences
Users need to be deliberate, especially in move mode. The session log provides enough information to reverse operations manually. We should make the log output clear and actionable. Undo remains a candidate for a future release.
