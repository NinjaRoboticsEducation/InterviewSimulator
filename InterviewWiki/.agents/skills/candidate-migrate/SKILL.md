---
name: candidate-migrate
description: Automatically synchronize derived candidate facts from a strictly reviewed PersonalWiki without modifying PersonalWiki.
---

# Candidate Migrate

1. Run `uv run interviewwiki personal status` and stop if strict readiness fails.
2. Run `uv run interviewwiki candidate status`.
3. If current, report the validated fact count and finish without rewriting the index.
4. If stale, run `uv run interviewwiki candidate migrate`.
5. Inspect the migration diff, validation, manifest, and walkthrough under `.interviewwiki/candidate-migrations/`.
6. Confirm that the migration reports `personal_wiki_unchanged: true`.
7. Return additions, changes, retirements, unresolved facts, source coverage, and the relative walkthrough path.

This workflow is automatic and does not pause for approval because its write scope is derived InterviewWiki runtime only. Never edit PersonalWiki, import generated output, or mark ambiguous experience as confirmed.
