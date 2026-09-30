# Shared Generation Contract

This contract applies to every AI coding tool. The JSON Schemas are authoritative when this document and a schema differ.

## Required order

1. Read normalized opportunity sources and create atomic `requirements.json` entries.
2. Query confirmed candidate facts; do not read generated resumes as evidence.
3. Map every requirement to `match`, `partial`, `gap`, or `unknown` in `match-analysis.json`.
4. Write SWOT, recruiter concerns, and preparation advice with fact/requirement IDs where applicable.
5. Create realistic questions and answers in `answer-plans.json`; each answer uses confirmed facts and STAR only when appropriate.
6. Create bilingual Method v1 `resume-content.json`. Paired blocks use identical block IDs and fact ID sets; the fixed sidebar/main section contract may not be changed.
7. Record every material candidate claim in `claim-ledger.json`.
8. Render user-facing Markdown and HTML only after structured artifacts validate.

## Writing rules

- Preserve facts while improving clarity and relevance.
- Do not copy job-description wording unless it accurately describes an existing candidate fact.
- Use concise, natural answers rather than scripts the candidate would have to memorize verbatim.
- Distinguish an actual gap from a weakly evidenced match.
- Keep company research, candidate evidence, and analyst inference visibly separate.
- Japanese wording must not strengthen, quantify, or broaden the English claim.
- Write Self Introduction as two or three natural, conversational but professional paragraphs that give a comprehensive overview of relevant strengths and experience.
- Write Self PR as two or three humble, sincere paragraphs centered on practical reasons for pursuing this work: the problems the candidate wants to solve, the next step in their career path, and how the role connects to work they have already done. Ground it in at least one specific responsibility, achievement, project, or portfolio case and explain its relevance to the position. Company mission or business direction may provide brief context, but must not be the main reason for interest. Avoid generic admiration and hard-sell language.
- Use concise sidebar skill names such as `UI/UX`; keep explanations in the main expertise blocks.
- Give each recent Professional Experience entry two or three distinct, grounded Responsibilities and two or three distinct, grounded Key Achievements. Responsibilities should show owned scope, methods, collaboration, and decisions; achievements should show shipped work, adoption, user or business outcomes, or supported metrics. Keep one contribution per bullet, begin with a clear action, and do not repeat or split one claim merely to reach the count. If fewer than two distinct facts are supported, record an evidence gap instead of inventing filler; the resume cannot pass strict final validation until the role is expanded from PersonalWiki evidence or moved to Earlier Career.
- Keep the resume ATS-readable: use standard section labels, plain-text role and skill terminology, and relevant job keywords only when candidate evidence supports them. Prefer specific tools, methods, domains, scope, and outcomes over adjectives, slogans, keyword stuffing, or claims copied from the job description.
- Use only an optional canonical portrait named `Profile.png`, `Profile.jpg`, or `Profile.jpeg` under `PersonalWiki/raw/media`; rendering handles it automatically for both locales and PDFs.

## Continuation and stop conditions

Continue when candidate evidence is missing: record a `gap`, `unknown`, or `candidate-confirmation-required` item, omit it from assertive answers/resume claims, and finish every unaffected artifact.

Stop only when PersonalWiki strict readiness fails, a source or path boundary is unsafe, the opportunity has no usable source, candidate data would leave the local boundary, or an artifact cannot be repaired to deterministic validity. Never solve a validation error by weakening the schema, relabeling an unsupported claim, or inventing support.

Routine writes limited to `.interviewwiki/`, `JobDescriptions/<company>/<opportunity>/_derived/`, and `Output/<company>/<opportunity>/` do not require an intermediate approval pause. Return the plan, changes, evidence gaps, and validation results in the final walkthrough.
