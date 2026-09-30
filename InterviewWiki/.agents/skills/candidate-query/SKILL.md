---
name: candidate-query
description: Retrieve confirmed candidate facts from PersonalWiki for matching, interview answers, and resumes. Use for read-only candidate analysis; do not use to add or modify personal information.
---

# Candidate Query

Run `uv run interviewwiki candidate build`, then search with `uv run interviewwiki candidate search "QUERY"`.

Use only returned `fact_id` values and their evidence. Treat `needs-review` facts, conflicts, and missing facts as gaps. A requirement in the job description does not imply the candidate has that skill.

This workflow is read-only. If the user wants to add or correct personal information, stop generation and use the reviewed LLMWiki workflow inside `PersonalWiki/`. Generated content must never be imported into PersonalWiki.
