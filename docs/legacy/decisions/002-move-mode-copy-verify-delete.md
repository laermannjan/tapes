# ADR-002: Move mode uses copy → verify → delete, not atomic rename

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
Move mode copies the file, verifies the SHA-256 checksum, writes the DB record, then deletes the source. The source file is never deleted before the DB record is written.

## Why
A crash mid-rename would leave the file orphaned at the destination with no DB record, and the source gone. There is no recovery path from that. The copy-verify-delete sequence keeps the source intact until we can prove the destination is good.

## Alternatives considered
- **Atomic os.rename()**: one syscall, no window for failure — but only works within the same filesystem, and gives no checksum guarantee.
- **Rename then write DB**: simplest but source is gone before the record exists.

## Consequences
Move operations take longer (full copy + hash). Cross-filesystem moves are handled the same way, which is convenient. Same-filesystem renames within the library (e.g. `tapes move`) still use `os.rename()` where source and dest are on the same device — that case is not an import operation.
