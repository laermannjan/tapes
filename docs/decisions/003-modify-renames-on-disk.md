# ADR-003: tapes modify renames files on disk by default

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
`tapes modify` updates metadata and renames the file to match the new metadata by default. `--no-move` suppresses the rename. This mirrors beets' `beet modify` behaviour.

## Why
After correcting a wrong match, the filename is almost certainly wrong too. Making the user run a second command to fix the name is surprising. Renaming by default is the expected behaviour if you've used beets, and it matches the principle of least surprise for a library organiser.

## Alternatives considered
- **Metadata-only by default, --move to rename**: safer but unintuitive. Users who fix a wrong identification would always need to remember to pass --move.
- **Always rename, no flag**: considered, but --no-move is useful for scripting and edge cases.

## Consequences
`tapes modify` is the primary correction workflow. It reuses the import identification pipeline. The command was originally called `tapes fix` — renamed to `tapes modify` to match the beets mental model.
