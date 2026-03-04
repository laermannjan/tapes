# ADR-011: GitHub as primary remote, Codeberg as mirror

**Status:** Accepted | **Date:** 2026-03-04

## What we decided
The primary repository is on GitHub (https://github.com/laermannjan/tapes). Codeberg will be added as a secondary mirror when convenient.

## Why
GitHub gives better reach for a developer CLI tool: more discoverability, mature CI (GitHub Actions), trusted publishing to PyPI, and a larger pool of potential contributors. The ethics argument for Codeberg (non-profit, FOSS, GDPR) is real but not decisive for a tool that benefits from community adoption.

## Alternatives considered
- **Codeberg only**: principled choice, but smaller audience and weaker CI ecosystem for a Python tool at this stage.
- **GitHub only**: simplest. We're adding Codeberg as a mirror anyway, so no real downside to having both.

## Consequences
CI/CD will run on GitHub Actions. Issues and PRs live on GitHub. Codeberg is a read mirror — it gives visibility to users who prefer it, with no extra maintenance burden if push-to-both is set up as a git remote.
