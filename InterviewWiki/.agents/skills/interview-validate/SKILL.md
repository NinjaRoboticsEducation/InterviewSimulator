---
name: interview-validate
description: Audit one InterviewWiki output for schemas, candidate grounding, requirement coverage, bilingual fact parity, unsupported values, and completeness.
---

# Interview Validate

Run `uv run interviewwiki validate REFERENCE` while drafting and `uv run interviewwiki validate REFERENCE --strict` before completion.

Fix schema and referential errors at their source. Do not weaken validators, delete legitimate gaps, invent facts, or mark unsupported claims as supported. Review every `unsupported-number`, unknown fact, unconfirmed fact, parity error, incomplete requirement match, and unfinished artifact.

Strict validation must finish with zero errors. Report warnings and factual gaps even when the run passes.
