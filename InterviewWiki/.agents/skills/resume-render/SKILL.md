---
name: resume-render
description: Render and verify the canonical bilingual InterviewWiki resume from validated structured content. Use for HTML resume generation and optional local PDF output.
---

# Resume Render

Edit `Evidence/resume-content.json`, not the HTML template or generated HTML. Use schema version 2 and `template_id: method-v1`. English and Japanese blocks must use the same block IDs, fact IDs, dates, numbers, qualifiers, and links.

1. Validate the opportunity.
2. Detect exactly one optional user photo at `PersonalWiki/raw/media/Profile.png`, `Profile.jpg`, or `Profile.jpeg`. Never source a portrait from generated output or any other path. Rendering automatically copies a valid photo into the opportunity-local `Resume/assets/` directory and uses it in both locales and PDFs.
3. Confirm every recent role contains two or three distinct, grounded Responsibilities and two or three distinct Key Achievements. Responsibilities must show supported scope, methods, collaboration, or decisions; achievements must show supported delivery, adoption, user or business outcomes, or metrics. Do not repeat, paraphrase, or split one fact simply to meet the count. If evidence cannot support two distinct bullets in each category, report the gap and move a non-detailed older role to Earlier Career rather than inventing content. Include every confirmed earlier employment record that predates the oldest detailed recent role in Earlier Career. Use concise ATS-readable skill labels.
4. Confirm Self PR is practical and personal: it explains the candidate's career direction and interest in the actual work, cites at least one concrete project, portfolio case, responsibility, or achievement, and connects that case to the role. Company mission must not be the primary reason for interest.
5. Run `uv run interviewwiki resume render REFERENCE`.
6. Inspect the generated HTML in both languages and verify the Method sidebar/main hierarchy, standard headings, selectable plain text, photo, responsive layout, accessibility state, and print layout. In A4 output, no experience, earlier-career table, expertise block, or Self PR block may split across pages.
7. Use `--pdf` only when a supported local browser is installed; HTML remains the required artifact.
8. Run strict validation after rendering.

Preserve factual accuracy and the fixed Method structure. Never use remote fonts, external rendering assets, inline event handlers, image-only text, or job-description wording unsupported by candidate facts. Reject PDFs containing browser headers/footers or local filesystem paths.
