# ADR-012: Use ADRs for design decisions, git log for change history

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
Significant design decisions are captured as ADRs in `docs/decisions/`. Design documents (`docs/design.md`, `docs/implementation-plan.md`) do not maintain an in-file changelog — git commit history serves that purpose.

## Why
Git log answers "what changed and when." ADRs answer "why was this approach chosen over alternatives." The second question is not answerable from a diff. Rejected alternatives are invisible in a living document — they need a dedicated record.

In-file changelogs get stale, add noise, and duplicate what git already does. ADRs are immutable once accepted — they are never edited to reflect later changes, only superseded by a new ADR.

## Alternatives considered
- **In-file changelog**: too much maintenance, duplicates git, gets inconsistent.
- **Git log only**: doesn't capture rejected alternatives or reasoning.
- **Full formal ADRs (Nygard format)**: heavier than needed for a small team. Our format is deliberately loose.

## Consequences
When a significant decision is made or reversed, a new ADR is written. Commit messages on design doc changes should be descriptive enough to serve as the change log ("docs: rename fix → modify — aligns with beet modify").
