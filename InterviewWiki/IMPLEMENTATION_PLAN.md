# InterviewWiki Implementation Plan

Status: **Final and implemented — architecture decisions approved on 2026-08-29**  
Audit date: 2026-08-29  
Audited scope: `resume/`, `InterviewWiki/`, `InterviewWiki/PersonalWiki/`, and `LLMWiki_Integration_Research.md`

## 1. Executive recommendation

Build InterviewWiki as a deterministic local application whose AI coding tool is an interchangeable reasoning client, not the owner of the workflow.

The canonical path should be:

```text
source files
  -> deterministic normalization and hashing
  -> typed opportunity and candidate evidence bundles
  -> AI-authored structured drafts
  -> deterministic provenance and quality gates
  -> Markdown and bilingual HTML outputs
```

Codex, Claude Code, Google Antigravity, and Cursor should all call the same CLI/service, read the same skills, emit the same schemas, and pass the same validators. MCP should be a thin optional interface over that service. It should not contain separate business logic.

Exact prose will still vary by model. Consistency should therefore mean identical inputs, required sections, evidence rules, provenance, validation gates, and output layout—not byte-identical wording.

The existing LLMWiki engine is a strong foundation for immutable sources, hashing, plans, lint, and safe writes. It is not yet sufficient by itself for candidate-fact grounding, job matching, web-research capture, bilingual parity, resume rendering, or end-to-end run orchestration.

## 2. Audit findings

### 2.1 Existing `resume` project

The `resume` directory is an asset collection and a history of manually materialized outputs, not a reusable resume-generation application.

| Area | Finding | Consequence |
| --- | --- | --- |
| Generator | No general generator, CLI, package manifest, render command, or test suite exists. | InterviewWiki cannot safely “call the existing generator” yet. |
| Named template | `Template/` is an old CodePen demo with placeholder content and remote GSAP/fonts. | It is not the template used by the recent bilingual resumes. |
| Actual design | Recent outputs share a newer bilingual HTML/CSS structure, but the HTML and CSS are duplicated per company. | One of these outputs must be promoted into a canonical source template. |
| Content | `Personal_Info/` contains a base resume, introductions, portfolio compilation, and several job-tailored resume variants. | Generated variants must not become candidate truth or they will create circular evidence. |
| Portfolio | Sixteen project files already use Situation/Task, Action, and Result in English, Japanese, and Traditional Chinese. | These are high-value PersonalWiki ingestion sources and Q&A evidence. |
| Job inputs | Seven Markdown job descriptions exist. | They are useful migration fixtures for the new opportunity workflow. |
| HTML behavior | Recent resumes contain English/Japanese pages, a language toggle, print CSS, a shared profile image, and semantic headings. | The structure is reusable after extraction and normalization. |
| ATS | The design is visually two-column and has no automated text-order or parser test. | ATS compatibility is presently unproven. |
| PDF | Existing PDFs appear to have been produced manually; no checked-in browser/PDF render workflow exists. | Rendering and visual QA must be implemented. |
| Assets | Fonts are fetched remotely, profile images are duplicated, and some links contain tracking parameters. | Offline determinism, privacy, and source hygiene need work. |
| Portability | A directory named `GeneralUI:UX` and case variants such as `resume`/`Resume` are present. | This is unsafe for consistent cross-platform tooling. |
| Repository hygiene | The directory is about 930 MB, mostly generated PDFs, screenshots, mockups, and duplicated assets. | Source, fixtures, and generated artifacts should be separated. |
| Font script | `refine_fonts.py` rewrites one generated CSS file in place using global string substitutions. | It is not a safe reusable design or build component. |

Reusable resume assets:

- The recent bilingual DOM structure and language toggle.
- The common print-oriented design in `output_resume/AIRoA`, `OpenAI`, `Pinterest`, `Socpely`, and `woven`.
- `Personal_Info/Profile.png` as the canonical source image, subject to privacy policy.
- The base resume and the sixteen STAR-form portfolio records as migration inputs.
- Existing job descriptions and outputs as regression fixtures only.

Do not reuse as architecture:

- Per-company copied HTML/CSS as editable source.
- Tailored resumes as evidence of candidate facts.
- `Template/` as the canonical modern design without an explicit user decision.
- Generated PDFs, browser profiles, PSD files, screenshots, or `.DS_Store` files.

### 2.2 Existing `InterviewWiki` scaffold

Current root content:

- `JobDescriptions/` is empty.
- `Output/Company/Interview/` and `Output/Company/resume/` are empty placeholders; `resume` conflicts with the requested `Resume` casing.
- Root `.agents/skills/` is empty.
- Root `AGENTS.md` contains LLMWiki-specific instructions for `raw/` and `wiki/`, although those folders exist only under `PersonalWiki/`.
- Root has no `CLAUDE.md`, `.claude/skills`, `.cursor/rules`, `.cursor/commands`, project configuration, schemas, CLI, tests, or README.
- The root is not a Git repository. `PersonalWiki/` is a nested Git repository.

This is an important discovery problem. A coding agent launched at `InterviewWiki/` will not reliably discover adapters stored only inside the child `PersonalWiki/` project. The current scaffold therefore supports working *inside the wiki*, but not the requested root-launched InterviewWiki workflow.

### 2.3 Existing PersonalWiki/LLMWiki implementation

The copied LLMWiki v0.2.1 implementation contains:

- Safe project-relative configuration and path containment.
- Raw source registration with SHA-256 hashes and source records.
- UTF-8 Markdown/text/HTML, text-bearing PDF, PNG, and JPEG normalization.
- Optional Tesseract OCR and sanitized image renditions.
- OKF Markdown frontmatter parsing that preserves unknown fields.
- Keyword search with status, trust, and stale-state reporting.
- JSON Schemas for source records, OKF profiles, and change plans.
- Plan validation with source hashes, target hashes, path rules, risk levels, and no-op protection.
- Locked, staged, linted, atomic bundle/catalog replacement with recoverable backups.
- Lint for metadata, links, citations, source drift, assets, possible secrets, and semantic-review state.
- Semantic-review hashes that become stale when meaning-bearing content changes.
- Canonical skills and adapters for Codex, Antigravity, Claude Code, and Cursor when launched in the wiki directory.
- Unit, integration, acceptance, and hostile-source tests.

Verification performed during this audit:

- `llmwiki doctor`: healthy.
- `llmwiki lint --format json`: no findings on the blank wiki.
- Test suite: a first post-install run showed one transient search assertion; the isolated test and a complete rerun both passed, ending at **61 passed**. Add a clean-environment CI run during implementation to rule out copied-environment state.

Limitations relevant to InterviewWiki:

- The wiki is still blank and contains no candidate facts.
- Search is token-based and includes robotics-specific equivalence groups; it is not a domain-neutral candidate retrieval system.
- PDF support excludes scanned PDFs and preserves text, not layout or form editability.
- The CLI is rooted in the current working directory and has no multi-root application service.
- There is no stable Python service/API layer, MCP server, research provider, candidate schema, claim ledger, job-matching engine, resume renderer, or end-to-end run manifest.
- Plan approval is a Boolean CLI flag, not an approval record bound to a plan digest and actor.
- Semantic review is page-level; it does not prove that every generated candidate claim is supported.
- The engine is duplicated inside the PersonalWiki data folder, including its own Git repository and local virtual environment.

### 2.4 Research document

The existing research correctly recommends three layers:

1. LLMWiki core for evidence and deterministic safety.
2. A stable application service for typed operations and policy.
3. Skills, CLI, ADK, and MCP as interfaces over the same service.

InterviewWiki should adopt this pattern. It should not start with ADK or a remote service. A local CLI plus repository skills produces the first useful version, while a local read-mostly STDIO MCP server can be added after the service contract stabilizes.

## 3. Required invariants

These rules should be enforced in code and schemas, not left only in prompts:

1. PersonalWiki is the only authority for candidate claims.
2. A job description can establish a requirement, never a candidate qualification.
3. Company research can establish company/role context, never candidate experience.
4. Generated resumes, interview answers, and prior tailored outputs are never evidence sources.
5. Every material candidate claim in an intermediate artifact maps to one or more immutable `fact_id` values.
6. Facts map to PersonalWiki page/source IDs and current hashes.
7. Numeric results, dates, employer names, job titles, certifications, languages, and named skills require exact supporting evidence.
8. Missing evidence becomes `unknown`, `gap`, or a question for the user; it must not be completed from model memory.
9. English and Japanese outputs use the same underlying facts and requirement mappings.
10. Web pages, PDFs, OCR, and pasted job descriptions are untrusted data and cannot override repository instructions.
11. Permanent PersonalWiki changes continue to use reviewed LLMWiki plans.
12. Generated opportunity outputs may be replaced only through a run manifest and an explicit target opportunity.

## 4. Recommended architecture

```text
AI coding tool
  |  root instructions + focused skill
  v
InterviewWiki CLI / optional MCP
  |
  +-- OpportunityService ----> JobDescriptions/<company>/<opportunity>/
  +-- CandidateService ------> PersonalWiki evidence + candidate fact index
  +-- ResearchService -------> captured company/role sources
  +-- PreparationService ----> structured drafts and claim ledger
  +-- ResumeService ---------> canonical bilingual HTML template
  +-- ValidationService -----> provenance, parity, ATS, HTML, render gates
  |
  v
Output/<company>/<opportunity>/<run manifest + deliverables>
```

### 4.1 One canonical Python service

Create a typed `InterviewWikiService` and a small `interviewwiki` CLI. Business logic must live here, not in skills, editor rules, shell snippets, or MCP handlers.

Initial service operations:

```text
opportunity_init(company, role, source_paths)
opportunity_inspect(opportunity_id)
opportunity_normalize(opportunity_id)
candidate_status()
candidate_search(query, filters)
candidate_read_fact(fact_id)
research_add(opportunity_id, url_or_file, metadata)
evidence_build(opportunity_id)
draft_validate(opportunity_id, artifact_path)
resume_render(opportunity_id, locale_mode)
run_validate(opportunity_id, strict)
run_publish(opportunity_id, run_id)
```

Each function returns a structured object and stable error codes. The CLI emits text for humans and JSON for agents/CI.

### 4.2 LLMWiki integration

Use the existing LLMWiki engine for PersonalWiki source/catalog/page integrity. Add an application adapter instead of parsing colorful CLI output.

Recommended refactor:

- Move reusable LLMWiki code to one package such as `packages/llmwiki-core/`, or depend on one separately versioned local package.
- Keep `PersonalWiki/` as a data instance: `llmwiki.yaml`, `raw/`, `wiki/`, and runtime state.
- Remove copied `.venv`, cache files, and nested repository metadata from the distributable scaffold after preserving history intentionally.
- Add explicit-root service construction; never rely on process CWD.
- Preserve current hashes, locks, plans, lint, backups, and hostile-source protections.

Do not let interview generation write new candidate facts. Missing or corrected personal information must go through a separate PersonalWiki ingest/review/apply workflow.

### 4.3 Candidate fact layer

OKF pages are good human-readable knowledge, but generated outputs need a finer grounding contract. Build a derived, reproducible candidate fact index from reviewed PersonalWiki pages.

Suggested fact shape:

```yaml
fact_id: fact-career-groupm-role-001
kind: employment | responsibility | achievement | skill | project | education | language | award
statement: "..."
subject: candidate
valid_from: 2020-01
valid_to: 2024-03
qualifiers: {}
evidence:
  - wiki_page: entities/employment/groupm.md
    source_id: src-...
    source_hash: sha256:...
confidence: confirmed | needs-review
sensitive: false
```

The index is derived and never hand-edited. It should be rebuilt deterministically and rejected if PersonalWiki lint or required semantic reviews fail.

### 4.4 Opportunity and research evidence

Keep candidate evidence and opportunity evidence in separate namespaces.

An opportunity contains:

- Company, role, location, source URL, application date, and optional job ID.
- Original Markdown/PDF files with hashes.
- Normalized text.
- A structured requirement matrix: required, preferred, responsibilities, outcomes, culture, hiring-process signals, and unknowns.
- Captured research source records with URL, title, publisher, retrieved time, publication/update time when known, hash/snapshot, source type, and claim usage.
- A research report that distinguishes direct source claims from analyst inference.

Research source priority:

1. Official company career, product, investor, engineering, policy, and newsroom pages.
2. Official filings and primary interviews.
3. Reputable industry or news sources when primary sources do not answer the question.
4. Job-review or forum content only as clearly labeled anecdotal evidence.

Do not make live browsing a hidden prerequisite for validation. Capture research into the opportunity folder so every tool sees the same evidence on subsequent runs.

### 4.5 Structured generation stages

The coding agent should never write final prose directly from a broad prompt. Require these stages:

1. `opportunity.json`: normalized opportunity metadata.
2. `requirements.json`: atomic job requirements with `requirement_id` values and source citations.
3. `candidate-selection.json`: relevant `fact_id` and project selections only.
4. `match-analysis.json`: evidence-backed matches, gaps, risks, and confidence.
5. `answer-plans.json`: question intent, selected facts, STAR fields, and prohibited unsupported claims.
6. `resume-content.json`: bilingual content blocks, each carrying the same fact references.
7. User-facing Markdown and HTML rendered from the validated structured artifacts.
8. `claim-ledger.json`: every material candidate claim, locale, output location, fact IDs, and validation result.

The structured stages create review points and make model differences measurable.

## 5. Proposed repository structure

```text
InterviewWiki/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── interviewwiki.yaml
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .agents/
│   ├── skills/
│   │   ├── interview-prepare/SKILL.md
│   │   ├── opportunity-ingest/SKILL.md
│   │   ├── company-research/SKILL.md
│   │   ├── candidate-query/SKILL.md
│   │   ├── interview-validate/SKILL.md
│   │   └── resume-render/SKILL.md
│   ├── workflows/                 # Antigravity adapters
│   └── rules/
├── .claude/skills/                # Thin wrappers or links to canonical skills
├── .cursor/
│   ├── rules/
│   └── commands/                  # Optional command adapters
├── .codex/config.toml             # Optional project-scoped local MCP
├── JobDescriptions/
│   └── <company-slug>/
│       └── <opportunity-slug>/
│           ├── opportunity.yaml
│           └── sources/            # Original MD/PDF/company files
├── PersonalWiki/                   # One data instance, not another app copy
│   ├── llmwiki.yaml
│   ├── raw/
│   └── wiki/
├── templates/
│   └── resume/
│       ├── index.html.j2
│       ├── styles.css
│       ├── script.js
│       ├── assets/fonts/
│       └── template-version.yaml
├── schemas/
│   ├── opportunity.schema.json
│   ├── requirements.schema.json
│   ├── candidate-fact.schema.json
│   ├── match-analysis.schema.json
│   ├── answer-plans.schema.json
│   ├── resume-content.schema.json
│   ├── claim-ledger.schema.json
│   └── run-manifest.schema.json
├── src/interviewwiki/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── services/
│   ├── validators/
│   ├── renderers/
│   └── mcp_server.py
├── packages/llmwiki-core/          # If the core is vendored here
├── prompts/                        # Versioned shared generation contracts
├── evals/
├── tests/
└── Output/
    └── <company-slug>/
        └── <opportunity-slug>/
            ├── Interview/
            │   ├── candidate-analysis.md
            │   └── interview-q-and-a.md
            ├── Resume/
            │   ├── index.html
            │   ├── styles.css
            │   └── assets/
            ├── Evidence/
            │   ├── requirements.json
            │   ├── research.md
            │   ├── research-sources.yaml
            │   ├── match-analysis.json
            │   └── claim-ledger.json
            └── Reports/
                ├── run-manifest.json
                └── validation.json
```

Use `Output/<company>/<opportunity>` instead of only `Output/<company>` so repeat applications and multiple roles cannot overwrite each other. The visible company grouping still satisfies the requested company-folder workflow.

## 6. Resume generation design

Promote one recent bilingual design into a real source template. Use Jinja2 or another small deterministic renderer; do not ask each model to hand-author HTML.

Requirements:

- One validated `resume-content.json` is the content source.
- English and Japanese sections share stable content-block IDs and fact IDs.
- HTML is semantic and usable without JavaScript.
- DOM reading order is ATS-friendly even if CSS creates a visual sidebar.
- The language switcher enhances the page but is not required to access either locale.
- Contact data, profile image inclusion, and public links are config-controlled.
- Fonts are stored locally or use a declared system stack for offline rendering.
- Print CSS has explicit A4 rules, page-break contracts, and no clipped content.
- External tracking parameters are stripped.
- `lang`, headings, link labels, alt text, and accessibility checks are enforced.
- Styled HTML is the required artifact. Optional PDFs are rendered from the same HTML, not edited separately.

ATS checks:

- Extract text in DOM order and compare required blocks with `resume-content.json`.
- Reject important text generated only with CSS, SVG, canvas, or images.
- Reject missing contact/experience headings and malformed dates.
- Check that every job-relevant term used in the resume is supported by candidate facts.
- Ensure role prioritization does not remove chronology or create unexplained dates.
- Produce a plain-text snapshot for review, but do not create a separate factual content path.

## 7. Skills and tool adapters

### 7.1 Canonical skills

Keep a small set of focused skills under root `.agents/skills/`:

- `interview-prepare`: orchestration and stage gates.
- `opportunity-ingest`: source discovery, normalization, requirement extraction, and injection defense.
- `company-research`: source-quality rules, capture, citations, and uncertainty.
- `candidate-query`: read-only PersonalWiki/fact retrieval and gap reporting.
- `interview-validate`: claim-ledger, bilingual, structure, and quality review.
- `resume-render`: validated resume JSON to HTML/render/visual QA.

Each skill should call the CLI for deterministic work, load only a small relevant reference, and define “done” as validator success. Avoid copying the whole operating manual into every skill.

### 7.2 Adapter strategy

| Tool | Root adapter |
| --- | --- |
| Codex | `AGENTS.md` plus canonical `.agents/skills/`; optional project `.codex/config.toml` for local MCP. |
| Claude Code | Root `CLAUDE.md` plus thin `.claude/skills/` wrappers/imports. |
| Antigravity | Root `.agents/rules/` and `.agents/workflows/` pointing to canonical skills. |
| Cursor | Root `AGENTS.md`, concise always-on `.cursor/rules/*.mdc`, and optional `.cursor/commands/*.md`. |

Adapters contain discovery syntax only. They must not fork workflow rules.

### 7.3 MCP

MCP is optional in the first release. When added, expose narrow structured operations:

```text
interview.opportunity.list
interview.opportunity.read
interview.candidate.search
interview.candidate.fact.read
interview.evidence.bundle.read
interview.draft.validate
interview.resume.render
interview.run.status
```

Write tools must accept an `opportunity_id`, reject arbitrary paths, and write only to run staging/output locations. PersonalWiki mutations remain behind LLMWiki plans and explicit approval. Start with a local STDIO server; remote HTTP, OAuth, ADK, and multi-user state are later concerns.

## 8. Anti-hallucination and validation design

Use layered validation because no single check is sufficient.

### Deterministic gates

- JSON Schema validation for every intermediate artifact.
- Referential integrity for every requirement ID, fact ID, page ID, source ID, and hash.
- Candidate-claim source separation: candidate claims may cite only candidate facts.
- Exact-value checks for dates, numbers, language levels, awards, employers, and job titles.
- Unsupported named-skill detection.
- Output section completeness and filename/casing checks.
- English/Japanese fact-set parity.
- HTML parsing, accessibility basics, link hygiene, and local-asset checks.
- Run-manifest input/output hashes and workflow/schema/template versions.

### Model-assisted review gates

- Recruiter-perspective concern review.
- Claim-to-evidence semantic entailment review.
- STAR authenticity and specificity review.
- Tone review for natural, non-scripted answers.
- Translation meaning review.
- “Too strong for evidence” review.

Model review findings cannot waive deterministic errors. Any unresolved unsupported claim fails strict validation.

### Claim ledger example

```json
{
  "claim_id": "resume-en-exp-003",
  "artifact": "Resume/index.html",
  "locale": "en",
  "text": "...",
  "fact_ids": ["fact-project-...", "fact-achievement-..."],
  "validation": "supported"
}
```

The published Markdown may keep citations readable or place them in a short evidence appendix. The machine-readable ledger is mandatory even when the user-facing resume omits visible citations.

## 9. Standard workflow

1. User creates or initializes an opportunity folder.
2. CLI inventories supported, changed, duplicate, and unsupported inputs.
3. CLI registers and normalizes Markdown/PDF sources and creates hashes.
4. Agent creates atomic requirements; validator checks source citations.
5. Agent researches the company/role when authorized, then captures sources locally.
6. CandidateService checks PersonalWiki health and builds/loads the candidate fact index.
7. Agent selects candidate facts and projects for each requirement.
8. Validator rejects job-description-derived candidate claims.
9. Agent drafts match analysis, SWOT, recruiter concerns, and preparation strategy.
10. Agent drafts question plans and evidence-backed STAR answers.
11. Agent drafts bilingual structured resume content.
12. Validators check claim support, exact values, parity, structure, and tone.
13. Resume renderer creates HTML from the canonical template.
14. Browser/render tests inspect desktop, mobile, print, and extracted text.
15. Strict run validation writes a report.
16. A successful staged run is published to the stable company/opportunity output folder.

On failure, keep the prior published output and leave the new run in staging with actionable errors.

## 10. Testing and evaluation strategy

### Unit tests

- Config and path containment.
- Opportunity naming and collision handling.
- Source hashing and normalization.
- Fact-index construction.
- Requirement/fact/claim referential integrity.
- Exact-value and unsupported-skill checks.
- Bilingual fact parity.
- HTML and manifest generation.

### Integration tests

- Markdown and text-PDF opportunity ingestion.
- Blank/scanned/encrypted/hostile PDF behavior.
- PersonalWiki query and drift handling.
- Full structured draft validation.
- Atomic staged output publishing and rollback.
- Resume render with local assets.
- Existing LLMWiki tests after the core refactor.

### Acceptance fixtures

Migrate several existing opportunities as fixtures, including at least:

- A design role.
- An AI/technical role.
- A strategy/marketing role.
- A deliberately poor match with requirements absent from PersonalWiki.

Expected assertions should cover facts and structure, not exact model prose.

### Cross-tool evaluation matrix

Run the same frozen evidence fixture through Codex, Claude Code, Antigravity, and Cursor. Record:

- Required artifact completion.
- Unsupported candidate-claim count (target: zero).
- Candidate claim precision and evidence coverage.
- Requirement coverage.
- English/Japanese fact parity.
- Validator pass rate without manual repair.
- Research citation quality and source-tier distribution.
- Resume render/ATS checks.
- Human recruiter rubric scores for usefulness, authenticity, and specificity.

Pin tool/model versions in the evaluation report. Do not claim tool-independent quality based on one run per tool.

### Adversarial tests

- Job description tells the agent to invent qualifications.
- Company page asks the agent to ignore repository rules.
- Candidate lacks a required skill that appears repeatedly in the JD.
- A prior tailored resume contains a claim absent from canonical sources.
- Conflicting dates or achievement metrics exist in PersonalWiki.
- OCR changes a number or employer name.
- Japanese translation strengthens an English claim.

## 11. Implementation phases

### Phase 0 — decisions and repository baseline

- Confirm Section 13 decisions.
- Initialize one root repository and preserve existing history intentionally.
- Add root README, config, ignore rules, and CI skeleton.
- Establish a migration backup before reorganizing files.

Exit: root instructions and a no-op CLI are discoverable from all four tools.

### Phase 1 — core extraction and canonical data

- Extract or depend on one LLMWiki core package.
- Convert `PersonalWiki/` into a clean data instance.
- Define candidate page types and fact schema.
- Ingest only canonical resume, career, portfolio, education, skill, and achievement sources.
- Mark conflicts and missing evidence; do not resolve them automatically.

Exit: PersonalWiki lint passes and a candidate fact index builds reproducibly.

### Phase 2 — opportunity model and CLI

- Add opportunity config, source normalization, requirement schema, and IDs.
- Migrate selected existing job descriptions as fixtures.
- Add staging/run manifests and stable output paths.

Exit: one Markdown and one PDF opportunity produce validated normalized evidence without LLM prose.

### Phase 3 — grounded preparation pipeline

- Add match analysis, answer plans, resume-content schema, and claim ledger.
- Implement deterministic validators and versioned prompts.
- Generate candidate analysis and Q&A Markdown from validated structures.

Exit: strict validation rejects every seeded unsupported claim.

### Phase 4 — canonical bilingual resume renderer

- Promote the selected design into a template.
- Add local fonts/assets, semantic DOM, ATS checks, print CSS, and Playwright rendering.
- Add optional PDF output only after HTML is stable.

Exit: English/Japanese HTML passes content, visual, print, and extracted-text checks.

### Phase 5 — cross-tool adapters

- Add canonical skills and thin adapters for all four tools.
- Add contract tests proving adapters reference the same skills and CLI.
- Run the frozen evaluation matrix.

Exit: all four tools produce schema-valid runs from the same fixture.

### Phase 6 — research adapter and MCP

- Add captured-source research contracts and source-quality validation.
- Add local read-mostly STDIO MCP over `InterviewWikiService`.
- Keep ADK and remote deployment out of scope unless a user-facing service is later required.

Exit: research is reproducible from captured evidence and MCP adds no duplicate business logic.

### Phase 7 — migration and pilot

- Migrate real PersonalWiki content with human review.
- Pilot two existing job opportunities.
- Compare new output with prior tailored resumes using the recruiter rubric.
- Document recovery, privacy, deletion, and update procedures.

Exit: user approves the first complete real opportunity run.

## 12. Key risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Tailored resumes contaminate truth | Ingest only canonical sources; treat old tailored outputs as regression samples. |
| Models infer candidate claims from the JD | Enforce source namespaces and fact IDs in code. |
| Root and nested instructions conflict | One root operating manual; specialized nested PersonalWiki rules only for PersonalWiki maintenance. |
| Tool output varies | Validate contracts and evidence, not exact prose. |
| Research changes over time | Capture retrieved sources, timestamps, hashes, and source tier. |
| Sensitive personal data leaves the machine | Local-first default, explicit research privacy policy, redacted fixtures, no secrets in prompts. |
| ATS conflicts with visual design | Semantic DOM order, extracted-text tests, and one factual content source. |
| Japanese wording overstates facts | Fact parity plus semantic translation review. |
| Nested Git/history is lost during cleanup | Back up and choose an explicit history-preservation migration. |
| PDF parsing silently loses content | Detect low/empty extraction and require OCR/manual transcription instead of continuing. |
| MCP broadens file access | Registry IDs only, no caller-supplied arbitrary paths, read-first tools. |
| Prompt files drift across tools | Canonical skill references and adapter contract tests. |

## 13. Approved architecture decisions

### Decision A — canonical resume design

Superseded by the approved 0.2 refinement: use the user-supplied `templates/Method/` HTML/CSS as the frozen golden reference. Production uses the sanitized, candidate-neutral, versioned `templates/resume/method-v1/` renderer with a fixed content hierarchy and configurable palette. The old CodePen `Template/` and the earlier AIRoA/woven promotion proposal are not part of the production architecture.

### Decision B — output granularity

Approved: use `Output/<company>/<opportunity>/` and `JobDescriptions/<company>/<opportunity>/` to support multiple roles and repeat applications.

### Decision C — PersonalWiki migration authority

Approved: treat `Personal_Info/Personal_resume.md`, `PersonalIntroduction.md`, and the individual `Personal_portfolio/*.md` files as candidate-source inputs. Exclude every job-tailored resume and generated HTML/PDF from candidate truth. User-authored personal information and generated information remain separated permanently; generated content is never written into PersonalWiki.

### Decision D — privacy and research mode

Approved: use local-first candidate processing. External research receives only company/role queries and never candidate PersonalWiki content. Captured public research may be saved under the opportunity.

### Decision E — PDF output

Approved: bilingual HTML is mandatory. Generated PDFs are optional and automated when a supported local browser is available.

## 14. Implementation completion criteria

Implementation is complete when the portable root CLI, schemas, candidate/opportunity separation, validators, canonical bilingual HTML renderer, optional PDF path, cross-tool adapters, automated tests, and documentation are present; the clean scaffold contains no copied test candidate or opportunity data; and a final portability scan finds no repository-specific absolute paths in application code or configuration.

## 15. Current documentation alignment

- OpenAI documentation describes skills as `SKILL.md` packages with optional scripts/references/assets and documents repository discovery under `.agents/skills` from the working directory up to the repository root.
- OpenAI documentation describes hierarchical `AGENTS.md` discovery from project root to working directory.
- OpenAI documentation supports project-scoped `.codex/config.toml` and local STDIO or Streamable HTTP MCP servers.
- Cursor documentation supports project rules under `.cursor/rules`, root `AGENTS.md`, commands under `.cursor/commands`, and structured non-interactive CLI output.
- Google Antigravity documentation supports directory-based `SKILL.md` packages and `.agents/workflows` commands.
- Claude Code documentation supports project `CLAUDE.md`, skills, MCP, and structured print-mode output.

## 16. Implemented baseline

The portable v0.2 implementation builds on the original v0.1 baseline through one shared Python service and CLI, versioned JSON Schemas, an automatic hash-verified candidate-fact migration, opportunity registration and normalized research capture, focused task modes, strict cross-artifact validation, the fixed Method v1 bilingual resume renderer, optional local PDF automation, and a narrow optional STDIO MCP adapter.

Canonical skills and thin adapters are present for Codex, Claude Code, Google Antigravity, and Cursor. Automated tests use temporary fictional fixtures only and cover the PersonalWiki no-write boundary, stale source rejection, opportunity research containment, schema/reference validation, unsupported numeric claims, bilingual parity, offline HTML output, root discovery, and path portability. The independently locked PersonalWiki suite is also verified from a clean environment.

The shipped `JobDescriptions/`, `Output/`, and derived runtime directories contain no candidate or opportunity fixture data. PersonalWiki remains a blank data instance; the existing nested Git history is preserved intentionally because deleting it would be irreversible and is not required for runtime portability.

These conventions change over time; adapter acceptance tests should be versioned and rerun during upgrades.
