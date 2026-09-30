---
name: compatibility-review
description: Produce a focused evidence-backed candidate and role compatibility review without generating unrelated resume or Q&A artifacts.
---

# Compatibility Review

1. Run `uv run interviewwiki task prepare REFERENCE --kind compatibility-review`.
2. Read the complete requirement set and confirmed candidate facts.
3. Write `match-analysis.json` using `match`, `partial`, `gap`, and `unknown` without positive or negative inference from absent evidence.
4. Write `Interview/candidate-analysis.md` titled “Candidate Experience & Compatibility Audit”.
5. Include requirement coverage, strengths, gaps, recruiter concerns, risks, and prioritized recommendations.
6. Run task-specific strict validation, repair generated artifacts, and finalize the task manifest.
7. Return a detailed walkthrough. Do not create resume or Q&A placeholders.
