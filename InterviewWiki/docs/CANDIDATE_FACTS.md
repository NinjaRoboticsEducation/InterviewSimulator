# Candidate Fact Contract

Candidate facts are machine-checkable, InterviewWiki-owned derived statements backed by semantically reviewed PersonalWiki pages and registered personal sources. Generated interview output is never an input.

A legacy PersonalWiki page may retain normal OKF `sources` entries and existing `candidate_facts` annotations:

```yaml
---
type: Entity
title: Candidate Career Evidence
description: Reviewed career facts from user-provided source material.
status: stable
sources:
  - id: src-YYYYMMDD-personal-resume
    resource: /references/personal-resume.md
    content_hash: sha256:<current-source-hash>
candidate_facts:
  - fact_id: fact-career-example-role
    kind: employment
    statement: A precise statement supported by the cited personal source.
    source_ids:
      - src-YYYYMMDD-personal-resume
    confidence: confirmed
    sensitive: false
    qualifiers: {}
---
```

Allowed kinds:

- `employment`
- `responsibility`
- `achievement`
- `skill`
- `project`
- `education`
- `language`
- `award`
- `portfolio`

Rules:

1. Each `fact_id` is stable, unique, lowercase, and starts with `fact-`.
2. Each fact cites at least one source listed by the same page.
3. Page and catalog source hashes must match.
4. Dates, metrics, job titles, language levels, and named skills stay in the fact statement when they are intended for generated output.
5. Use `needs-review` for unresolved conflicts. Strict generation rejects those facts.
6. Do not extract facts from job descriptions, company research, tailored resumes, generated HTML/PDF, or InterviewWiki output.
7. Personal truth is updated only through PersonalWiki's reviewed workflow.
8. InterviewWiki candidate migration writes only `.interviewwiki/candidate-facts.json` and migration reports; it never inserts generated metadata into PersonalWiki.
9. Existing embedded `candidate_facts` remain supported as legacy reviewed annotations, but InterviewWiki does not edit them.

Run `uv run interviewwiki candidate status` to check freshness and `uv run interviewwiki candidate migrate` to perform an automatic derived migration. Every downstream task performs the same freshness check automatically.
