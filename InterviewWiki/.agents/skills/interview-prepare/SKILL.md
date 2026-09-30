---
name: interview-prepare
description: Generate a complete evidence-grounded interview package for one registered InterviewWiki opportunity, including analysis, Q&A, and a bilingual resume. Use for the end-to-end preparation workflow.
---

# Interview Prepare

Work on exactly one `<company>/<opportunity>` reference. Read `AGENTS.md`, `prompts/generation-contract.md`, and the relevant schemas before drafting.

1. Run `uv run interviewwiki task prepare REFERENCE --kind full-package`. This automatically verifies PersonalWiki and refreshes stale derived candidate facts.
2. Read normalized opportunity evidence and captured research under that opportunity only.
3. Query candidate facts with `uv run interviewwiki candidate search "QUERY"`. Never use generated resumes or job descriptions as candidate evidence.
4. Fill `requirements.json`, `match-analysis.json`, `answer-plans.json`, `resume-content.json`, and `claim-ledger.json` to their schemas. In the resume, give every recent role two or three distinct, evidence-grounded Responsibilities and two or three distinct Key Achievements. Extract supported scope, methods, collaboration, shipped work, adoption, and outcomes that are relevant to the role; never duplicate or subdivide one claim to fill space. Carry confirmed older employment into Earlier Career, use concise ATS-readable skill tags, and write a natural two-or-three-paragraph Self Introduction.
5. Write Self PR as two or three sincere, practical paragraphs. Explain why the day-to-day work is a meaningful next step in the candidate's career, connect that motivation to at least one named real-world project, portfolio case, responsibility, or achievement, and state the supported capabilities they would bring. A company mission may be brief context but never the main motivation. Avoid generic admiration, slogans, keyword stuffing, and hard-sell language.
6. Write the candidate analysis and Q&A Markdown. Preserve gaps and recruiter concerns honestly.
7. Run non-strict validation, automatically correct generated-output errors, then render the fixed Method v1 resume. A canonical photo at `PersonalWiki/raw/media/Profile.png`, `Profile.jpg`, or `Profile.jpeg` is detected and embedded automatically; do not copy or edit it. Do not edit template HTML/CSS/JS.
8. Inspect both HTML locales and optional PDFs, confirm standard headings and selectable plain text remain ATS-readable, run strict validation, and finalize the manifest.

Do not stop the package for a missing candidate fact. Report the gap or confirmation question, omit the unsupported claim, and continue. Stop only for the root safety and technical conditions in `AGENTS.md`. Return a detailed walkthrough after completion; no routine intermediate approval is required.
