# InterviewWiki Refinement Plan

Status: **Implemented in InterviewWiki 0.2.0 on 2026-08-29; Method content/photo refinements completed in 0.2.1**  
Plan date: 2026-08-29  
Supersedes: the resume-design and workflow portions of `IMPLEMENTATION_PLAN.md` after approval  
Primary reference: `templates/Method/`

## 1. Executive decision

This refinement makes two product-level changes:

1. **Method becomes the canonical resume design and content contract.** The current generic resume renderer will be replaced by a versioned, sanitized production template derived from `templates/Method/index.html` and `templates/Method/styles.css`. AI tools will generate only validated structured content; they will not design or hand-author resume HTML/CSS.
2. **The workflow becomes intent-based and mostly automatic.** First-time candidate setup remains separate from job preparation, but candidate migration, opportunity ingestion, research, generation, repair, validation, rendering, and reporting will run without intermediate approval pauses. Users review a detailed walkthrough after each operation.

The simplification will not weaken the existing boundaries:

- PersonalWiki remains the only candidate evidence authority.
- Generated facts and job-tailored content never write into PersonalWiki.
- Candidate information remains local and is excluded from external research.
- Missing evidence is reported as a gap or confirmation question, not invented.
- All application paths remain project-relative and portable.

### 1.1 Implementation completion note

InterviewWiki 0.2.0 implements this plan in both the working application and the clean copy-and-paste template:

- Method v1 is a fixed bilingual structured-content schema plus deterministic HTML/CSS/JavaScript renderer; the palette remains configurable while layout and section order do not.
- Candidate migration performs strict PersonalWiki readiness checks, stages and validates a derived index, produces a diff and walkthrough, and proves that PersonalWiki was unchanged before publishing.
- Existing opportunity folders can be registered and ingested in one command; research records require local snapshots, provenance fields, and the `company-role-only` privacy classification.
- Full-package and focused task modes share one service/CLI contract and one manifest lifecycle.
- Legacy generated schema-v1 resumes have a recoverable Method upgrader; uncertain legacy interview answers remain explicitly confirmation-required.
- Atomic writes, operation locks, containment and symlink checks, stable content hashes, recursive artifact manifests, DOM/privacy validation, and PDF path scans are enforced.
- Codex, Antigravity, Claude Code, Cursor, optional MCP, README prompts, and canonical skills reflect the simplified first-run/subsequent-run flow.
- Automated regression, portability, clean-template, browser-responsive, and A4 PDF visual checks were completed for the 0.2 release.

## 2. Verified starting state

### 2.1 PersonalWiki

The updated PersonalWiki was checked with:

```text
uv run --locked llmwiki lint --strict --format json
```

Result: exit code 0 and an empty finding list. The current PersonalWiki therefore passes the strict metadata, provenance, source-hash, and semantic-review gate.

This must become an automated precondition rather than a fact users must remember to check manually.

### 2.2 Method resume reference

The Method HTML was inspected from source and rendered in both languages. Its canonical visible structure is:

```text
Language switcher
└── Resume locale
    ├── Left sidebar — 292px at the 1120px desktop layout
    │   ├── Profile photo
    │   ├── Candidate name
    │   ├── Contact
    │   ├── Languages
    │   ├── Skills
    │   ├── Tools
    │   ├── Education
    │   └── Awards
    └── Main content
        ├── Tailored headline
        ├── Self Introduction
        ├── Four-signal strip
        ├── Professional Experience
        │   ├── Responsibilities per recent role
        │   └── Key Achievements per recent role
        ├── Earlier Career table
        ├── Personal Expertise — four blocks
        └── Tailored Self PR
```

The reference uses a photo-led dark sidebar, warm paper background, white content sheet, red timeline accents, teal role accents, gold subheadings, compact tag chips, long-form experience entries, and explicit English/Japanese variants. This is materially different from the current generated resume, which uses a short right sidebar, no profile image, no signal strip, no responsibilities/achievements separation, no earlier-career table, no expertise grid, and no self-PR section.

The Method reference also contains implementation details that must be corrected during promotion:

- Google Fonts are loaded remotely; production must use local fonts or an approved system stack.
- JavaScript is inline; production must use the versioned local script asset.
- Switching to Japanese does not update the document-level `lang` value.
- Toggle buttons do not expose `aria-pressed` state.
- Candidate-specific content and the real profile image are embedded in the reference and must not become application defaults.
- Print behavior is tightly coupled to the reference content and must be made deterministic for generated variable-length content.

`templates/Method/` will remain a frozen golden reference. Production files will live in a versioned template directory so the example and generator cannot silently drift together.

## 3. Product behavior after refinement

### 3.1 First run

#### Step 1 — Initialize and review PersonalWiki

The user adds canonical personal sources, builds the PersonalWiki, and completes semantic review. This is the only workflow where candidate truth is created or corrected.

Completion gate:

- PersonalWiki doctor passes.
- Strict lint passes.
- Required source and semantic-review hashes are current.
- No generated resume, job analysis, or job-tailored material is registered as candidate evidence.

#### Step 2 — Synchronize candidate facts

The user can prompt:

> Synchronize candidate facts from my reviewed PersonalWiki. Complete the migration automatically, do not modify PersonalWiki, and return a detailed walkthrough.

The AI coding tool will:

1. run the PersonalWiki readiness gate;
2. calculate a stable fingerprint of reviewed candidate pages, source records, and semantic-review records;
3. compare it with the last candidate migration;
4. create a staged candidate-fact migration plan;
5. extract or refresh facts into InterviewWiki-owned derived state;
6. validate every fact against current page/source hashes and evidence excerpts;
7. classify ambiguity as `candidate-confirmation-required` rather than confirmed;
8. atomically publish the candidate fact index;
9. prove that the PersonalWiki tree hash did not change;
10. return a walkthrough showing additions, changes, retirements, unresolved items, source coverage, and validation results.

No approval pause is required because this operation writes only rebuildable InterviewWiki runtime state. It must never edit `PersonalWiki/raw/`, `PersonalWiki/wiki/`, its catalogs, reviews, or log.

This step is needed only when PersonalWiki changes. Downstream workflows will run the same fingerprint check automatically and refresh stale candidate facts, so the user does not need to remember it manually.

#### Step 3 — Add an opportunity manually

The user creates:

```text
JobDescriptions/<company>/<opportunity>/sources/
```

and adds the job description plus any user-supplied role material as Markdown. The folder path is the default portable opportunity identity.

`opportunity.yaml` may be absent initially. The registration workflow will create it from the folder identity and extracted job metadata, then report the chosen company, role, and slug.

#### Step 4 — Register, ingest, and research

The user can prompt:

> I added a new opportunity at JobDescriptions/<company>/<opportunity>. Register and ingest it, research the company and role using public sources only, capture the sources locally, and return a walkthrough.

The AI coding tool will perform one uninterrupted workflow:

1. validate the opportunity folder and supported source files;
2. create or update `opportunity.yaml` without overwriting explicit user metadata;
3. reject symlinks, traversal, files outside the opportunity, and unsupported/empty sources;
4. normalize and hash the supplied sources;
5. extract all material requirement categories;
6. research the company, product, role, working model, hiring process, and relevant current developments;
7. send only company/role queries externally;
8. capture claim-level source excerpts and metadata under the opportunity;
9. register and hash every source actually used;
10. preserve conflicts and distinguish source statements from analyst inference;
11. re-ingest the complete opportunity evidence bundle;
12. write a registration/research manifest and walkthrough.

If network research is unavailable, the workflow will finish registration and ingestion, mark research as incomplete, and explain what is missing. It will never fill the gap from model memory.

#### Step 5 — Generate a full package or a focused task

Full package prompt:

> Generate the complete interview preparation package for <company>/<opportunity>, including my experience and compatibility audit, interview Q&A, the Method-format bilingual resume, optional PDFs, strict validation, and a detailed walkthrough.

Focused prompt:

> Run only a compatibility review for <company>/<opportunity>. Compare the role with my confirmed PersonalWiki evidence, identify strengths, gaps, risks, and recommendations, and return the review and walkthrough.

Other supported focused intents will include:

- company/role research refresh;
- requirement analysis;
- compatibility review;
- recruiter-risk review;
- interview questions and evidence-backed answer planning;
- portfolio/project selection;
- resume content generation;
- resume rendering;
- validation/audit.

The agent will infer the task kind from natural language. It will run the deterministic CLI internally; the user will not need to translate the request into terminal commands.

### 3.2 Subsequent opportunities

The normal flow becomes:

1. add a new opportunity folder and Markdown source;
2. prompt the AI to register, ingest, and research it;
3. prompt for either the complete package or a focused task.

Every operation starts with a cheap PersonalWiki/candidate fingerprint check. If PersonalWiki changed, candidate synchronization runs automatically and is included in the walkthrough. If it did not change, the existing validated candidate index is reused.

### 3.3 Approval and pause policy

The application will not pause for routine intermediate review. It will plan, stage, validate, apply, and then show the result.

It will stop only when continuing would be unsafe or meaningless:

- PersonalWiki strict lint fails;
- a PersonalWiki source or semantic review is stale;
- the job description is missing or unreadable;
- an input crosses a path/security boundary;
- required external research is explicitly requested but unavailable and the requested result cannot be produced without it;
- a deterministic artifact cannot be repaired to schema validity;
- the requested action would modify PersonalWiki or disclose candidate data externally.

Missing candidate experience is not a stop condition. It becomes a documented `gap`, `unknown`, or `candidate-confirmation-required` item and is excluded from assertive resume/interview statements.

## 4. Canonical Method resume contract

### 4.1 Template ownership

Create:

```text
templates/resume/method-v1/
├── index.html.j2
├── styles.css
├── script.js
├── template-version.yaml
└── assets/
    └── fonts/
```

Set `paths.resume_template` to this project-relative directory. `templates/Method/` remains the visual/content golden reference and is not used as candidate truth.

The template version file will record:

- template ID and semantic version;
- reference design;
- required DOM IDs/classes;
- required and conditional sections;
- allowed CSS variables;
- renderer compatibility version;
- asset hashes;
- print contract version.

AI tools may edit `resume-content.json`; they may not edit the template, CSS, JavaScript, or generated HTML during an opportunity run.

### 4.2 Strict content schema

Upgrade `resume-content.schema.json` to version 2. The bilingual locale objects will use explicit Method fields rather than generic arbitrary sections.

| Area | Field/section | Contract |
|---|---|---|
| Identity | name | Required per locale; fact-backed or approved identity record |
| Identity | photo | Optional, config-approved, project-relative local asset |
| Sidebar | contact | Email, phone, website, LinkedIn, YouTube, location; common values with localized labels |
| Sidebar | languages | One or more evidence-backed language/level rows |
| Sidebar | skills | Evidence-backed tag list; qualifiers must be preserved |
| Sidebar | tools | Evidence-backed tag list; qualifiers must be preserved |
| Sidebar | education | One or more education records |
| Sidebar | awards | Conditional; omit the whole section when empty |
| Main | headline | Required, role-targeted, and fact-supported |
| Main | self introduction | Two or three concise paragraphs, each with block and fact IDs |
| Main | signals | Exactly four compact evidence-backed summary signals |
| Main | professional experience | Chronological recent roles with company, role, period, location, responsibilities, and achievements |
| Main | earlier career | Conditional table for older roles; never invent rows to fill the design |
| Main | personal expertise | Exactly four grouped capability blocks for this template version |
| Main | self PR | Two or three role-tailored paragraphs; candidate claims fact-backed, company motivation cited separately |

Each factual paragraph, signal, row, responsibility, achievement, expertise bullet, and self-PR claim receives a stable `block_id` and `fact_ids`. Links are modeled as structured link objects rather than embedded HTML.

The schema will reject:

- unknown or arbitrary sections;
- wrong section order;
- empty visible sections;
- unqualified skills when the fact carries a proficiency qualifier;
- HTML embedded in content strings;
- unregistered external asset URLs;
- missing fact IDs on candidate claims;
- English/Japanese block-set differences;
- date, number, link, or qualifier differences between locales.

### 4.3 Strict DOM contract

The renderer will always produce:

```text
body
├── nav.lang-toggle.no-print
├── article#resume-en.resume-page[data-language=en]
│   ├── aside.sidebar
│   └── main.main
└── article#resume-ja.resume-page[data-language=ja]
    ├── aside.sidebar
    └── main.main
```

Inside each locale, the class hierarchy and section order will match Method. All claim-bearing elements will include `data-block-id`; section containers will include `data-section-id`.

The validator will parse the generated DOM and reject missing, reordered, duplicated, or unexpected structural nodes. Generated HTML will be deterministic for the same validated JSON, template version, and assets.

### 4.4 Strict visual contract

The Method layout is fixed at the component level:

- 1120px desktop sheet with a 292px left sidebar;
- warm paper/grid page background and white sheet;
- circular profile image with the Method proportions;
- dark layered sidebar background;
- red accent for timeline/signals, teal for role headings, and gold for subheadings/award years;
- Method typography scale, spacing rhythm, border styles, tags, signal grid, timeline, tables, expertise grid, and self-PR panel;
- one-column responsive layout at the approved breakpoint;
- A4 print layout with deterministic page breaks.

Configuration may change only allowlisted design tokens such as palette values and optional photo visibility. It may not change column widths, section order, type scale, spacing scale, or component layout per opportunity. Palette overrides must pass contrast checks.

No remote fonts, CSS, JavaScript, tracking pixels, or render-time network requests are allowed. Noto Sans and Noto Sans JP will be vendored locally if licensing permits; otherwise use a declared portable system-font stack.

### 4.5 Interaction and accessibility contract

The local language script will:

- work without inline event handlers;
- update the active resume, document `lang`, button `aria-pressed`, and accessible status;
- support keyboard navigation and visible focus;
- honor `?lang=en` and `?lang=ja`;
- leave both language articles present in the source for deterministic extraction;
- avoid changing or fetching content at runtime.

The HTML will use semantic headings, lists, tables with proper headers, descriptive link text, local alt text, and no text represented only in images or CSS.

### 4.6 Print/PDF contract

HTML remains mandatory. When PDF output is enabled, the renderer will produce the configured set of:

- `resume-en.pdf`;
- `resume-ja.pdf`;
- `resume-bilingual.pdf`.

The controlled browser invocation must disable browser headers and footers. Validation will fail on:

- `file://`, absolute project paths, or temporary paths in extracted PDF text;
- clipped headings, missing glyphs, blank pages, incorrect locale, or unintended browser metadata;
- remote font/resource requests;
- page content outside safe print bounds;
- unreadable sidebar contrast.

All PDFs, HTML, CSS, JavaScript, local assets, template version, and renderer version will be included in the run manifest.

## 5. Candidate-fact migration redesign

### 5.1 PersonalWiki remains immutable during InterviewWiki work

Candidate migration will no longer require InterviewWiki to insert generated `candidate_facts` metadata into PersonalWiki pages.

The canonical write boundary becomes:

```text
PersonalWiki reviewed pages and sources       read only
                    ↓
.interviewwiki/candidate-migrations/<run-id>/ staged plan and evidence
                    ↓
.interviewwiki/candidate-facts.json           derived published index
```

Existing embedded `candidate_facts` may be consumed as legacy reviewed annotations during transition, but future InterviewWiki migrations will not add or edit them. Removing legacy metadata from PersonalWiki is not part of this refinement because that would be a separate user-authorized PersonalWiki change.

### 5.2 Migration artifacts

Each synchronization writes derived runtime artifacts:

- `plan.json`: source fingerprint, changed pages, extraction operations, and expected facts;
- `candidate-facts.staged.json`: complete proposed replacement index;
- `diff.json`: added, changed, retired, and unresolved facts;
- `validation.json`: schema, hash, entailment, duplicate, conflict, and sensitivity results;
- `manifest.json`: tool/model/version, inputs, outputs, and timestamps;
- `walkthrough.md`: human-readable review summary.

Publication is atomic. A failed migration keeps the previous validated candidate index and the failed staged report.

### 5.3 Stable freshness detection

The candidate source fingerprint must exclude volatile generated timestamps. It will be computed from canonical relative paths and content hashes for:

- applicable reviewed wiki pages;
- their source records and source hashes;
- their current semantic-review records;
- candidate extraction policy/schema version.

All downstream tasks call `candidate status`. A mismatch triggers automatic synchronization before candidate facts are queried.

## 6. Opportunity registration and automatic research

### 6.1 Combined intent, separated internal stages

To the user, registration, ingestion, and research are one step. Internally they remain separate so failures and provenance are clear:

```text
discover → register → ingest supplied sources → extract requirements
         → research → capture/register sources → re-ingest → validate
```

### 6.2 Research evidence contract

Add a validated `research-sources.schema.json`. Each research claim records:

- canonical source ID;
- exact URL used;
- title, publisher, source tier, and publication/update date when known;
- retrieval timestamp;
- project-relative snapshot path and hash;
- bounded supporting excerpt;
- direct-claim or analyst-inference classification;
- conflicts/uncertainty;
- external query classification proving that only company/role terms were used.

Do not label a synthesized summary as a source snapshot. Store captured excerpts separately from the generated research synthesis.

### 6.3 Complete requirement extraction

Expand requirement categories to cover:

- responsibilities and outcomes;
- required and preferred qualifications;
- location/eligibility;
- working arrangement and hours;
- travel and meeting requirements;
- compensation and benefits;
- hiring process and assessments;
- background/compliance conditions;
- privacy, AI use, consent, and application-accuracy terms;
- culture and operating model.

Validation will require every material source clause to have either a requirement record or a reviewed `not-applicable` disposition. Match coverage alone will no longer be accepted as proof of extraction completeness.

## 7. Full and focused task orchestration

### 7.1 Task model

Add a task/run manifest with a `task_kind`:

```text
full-package
compatibility-review
research-refresh
requirements-review
interview-qa
portfolio-selection
resume-content
resume-render
validation-audit
```

Each kind declares its required inputs, artifacts, validations, and completion criteria. Focused tasks will not be forced to create unrelated placeholder files.

### 7.2 Full package stages

The full package will run:

1. candidate freshness/readiness preflight;
2. opportunity/research freshness preflight;
3. complete requirement extraction;
4. evidence-backed compatibility analysis;
5. recruiter concerns, gaps, risks, and preparation recommendations;
6. question plan and grounded answer generation;
7. Method resume-content generation in English and Japanese;
8. exhaustive claim-ledger generation;
9. semantic evidence review and translation parity review;
10. Method HTML rendering and optional PDF rendering;
11. deterministic strict validation and automatic repair loop;
12. atomic publication and detailed walkthrough.

The compatibility analysis file can retain the existing portable filename `Interview/candidate-analysis.md`, but its title and contract will become **Candidate Experience & Compatibility Audit**. A focused compatibility request creates or refreshes this artifact plus only its required evidence files.

### 7.3 Automatic repair loop

The agent may automatically repair generated artifacts within the active opportunity. It may not repair PersonalWiki or source originals.

Repair is bounded:

- maximum configured attempts;
- every attempt logged with changed artifact hashes;
- deterministic errors must reach zero;
- semantic findings cannot be dismissed without changing or removing the claim;
- unsupported candidate statements are removed or marked as questions, never relabeled as supported.

## 8. Grounding, security, and integrity changes retained from the audit

The following audit remediations remain required and are incorporated into this plan:

1. Gate candidate usage on current PersonalWiki strict health.
2. Reject resolved-path escape and all source symlinks in candidate and opportunity ingestion.
3. Require exhaustive claim-ledger coverage for every factual resume and interview block.
4. Add semantic claim states: `supported`, `partially-supported`, `candidate-confirmation-required`, and `unsupported`.
5. Keep missing evidence as `unknown` rather than inferring a positive or negative fact.
6. Preserve proficiency qualifiers across facts, analysis, English, and Japanese.
7. Ground identity/contact fields separately and mark them sensitive.
8. Validate research records, snapshots, citations, and current hashes.
9. Use atomic staging, opportunity locks, validation-before-publish, and rollback.
10. Record stable input/output hashes, complete artifact coverage, tool/model/version, template version, and execution ID.
11. Add a privacy-preserving execution ledger and external-domain/query classification.
12. Delimit untrusted source text and add prompt-injection fixtures.
13. Validate bilingual dates, numbers, URLs, qualifiers, and semantic meaning—not only fact-ID parity.
14. Render and visually inspect PDFs; scan them for local path leakage.

## 9. CLI and service changes

The AI coding tool remains the natural-language interface. The CLI provides deterministic operations underneath it.

Proposed commands:

```text
interviewwiki personal status [--json]
interviewwiki candidate status [--json]
interviewwiki candidate migrate [--auto] [--json]

interviewwiki opportunity register <reference-or-folder>
interviewwiki opportunity ingest <reference>
interviewwiki opportunity status <reference>
interviewwiki research register <reference> ...
interviewwiki research validate <reference>

interviewwiki task prepare <reference> --kind <task-kind>
interviewwiki task validate <reference> --kind <task-kind> [--strict]
interviewwiki task finalize <reference> --kind <task-kind>

interviewwiki resume render <reference> [--pdf en|ja|bilingual|all]
interviewwiki run status <reference>
```

`InterviewWikiService` will expose matching typed methods. Agent skills and MCP remain thin adapters; they must not implement separate business rules.

## 10. Agent skills and Antigravity workflow changes

Add or revise canonical skills:

- `personalwiki-bootstrap`: first-run guidance and strict readiness checks;
- `candidate-migrate`: automatic derived migration and walkthrough;
- `opportunity-register`: combined registration, ingestion, research, and source capture;
- `compatibility-review`: focused candidate/role assessment;
- `interview-prepare`: uninterrupted full-package orchestration;
- `company-research`: claim-level source capture and privacy logging;
- `resume-render`: Method-only rendering and visual QA;
- `interview-validate`: task-aware strict validation.

Antigravity workflows will mirror these intents with concise commands, while ordinary natural-language prompts remain supported. Claude and Cursor wrappers will reference the same canonical skills. Root `AGENTS.md`, `README.md`, and `prompts/generation-contract.md` will be updated so they do not instruct the agent to stop for every missing fact or intermediate review.

The revised generation contract will say:

- continue the package with explicit gaps when evidence is missing;
- pause only on the safety/technical stop conditions in Section 3.3;
- never turn a proposed approach into claimed past experience;
- never require user approval for writes limited to derived runtime or opportunity output;
- always return a final walkthrough with actions, evidence gaps, validation, and files.

## 11. Implementation phases

### Phase 0 — Freeze references and add regression fixtures

- Preserve `templates/Method/` as the golden reference.
- Capture structural snapshots for both locales and controlled screenshots for desktop, responsive, and print states.
- Add a fictional Method-content fixture; do not use real candidate PII in automated tests.
- Record the current PersonalWiki strict-pass baseline without copying its data into fixtures.

Exit: reference hashes and expected Method hierarchy are frozen.

### Phase 1 — Method renderer and resume schema v2

- Create the sanitized `method-v1` production template.
- Replace generic resume sections with the strict Method schema.
- Add Jinja autoescaping with strict missing-field handling or an equivalently safe deterministic renderer.
- Vendor fonts or use the approved offline stack.
- Implement local assets, structured links, language behavior, and accessibility fixes.
- Implement print/PDF header suppression and manifest coverage.
- Add DOM, offline, parity, accessibility, print, and visual-regression tests.

Exit: a fictional bilingual resume matches the Method structure/design and passes offline HTML and PDF validation.

### Phase 2 — Read-only automatic candidate migration

- Add PersonalWiki strict preflight and stable source fingerprinting.
- Move generated candidate extraction/migration state entirely under `.interviewwiki/`.
- Add staged migration plan, validation, diff, manifest, atomic publication, and walkthrough.
- Add automatic stale detection to every candidate-consuming task.
- Prove byte-for-byte PersonalWiki immutability in tests.

Exit: adding/reviewing a wiki page causes one automatic derived migration; unchanged wikis are reused without work.

### Phase 3 — Combined opportunity registration and research

- Add register-from-folder behavior.
- Add source-boundary/symlink protections.
- Add complete requirement categories and source-clause dispositions.
- Add research schema, exact-source capture, conflicts, privacy query classification, and complete manifest hashing.
- Update the opportunity skill and Antigravity workflow to orchestrate registration, ingestion, and research as one user action.

Exit: one natural-language request produces a registered, researched, reproducible opportunity with no candidate data in external queries.

### Phase 4 — Full/focused task modes and automatic repair

- Add task kinds and conditional artifact requirements.
- Update the full preparation pipeline.
- Add focused compatibility, Q&A, resume, research, and audit modes.
- Replace routine approval stops with bounded automatic repair and final walkthroughs.
- Keep prior published output until a staged task passes its task-specific gates.

Exit: full and focused prompts complete without terminal interaction or intermediate approval.

### Phase 5 — Evidence, security, and manifest hardening

- Implement exhaustive claim coverage and semantic review states.
- Add exact qualifier/date/number/link parity.
- Add locks, atomic writes, rollback, stable hashes, complete manifests, and execution ledgers.
- Add prompt-injection and path-boundary tests.
- Add PDF path-leak, contrast, clipping, and glyph checks.

Exit: all high-priority audit findings are closed with regression tests.

### Phase 6 — Documentation, adapters, and clean-template release

- Rewrite the README around first-run and subsequent-run natural-language flows.
- Add copy-ready prompts for each intent.
- Update root rules, canonical skills, Antigravity workflows, Claude wrappers, Cursor commands, and optional MCP descriptions.
- Update `IMPLEMENTATION_PLAN.md` decisions and version history.
- Propagate application changes to `InterviewWikiTemplate` without candidate facts, opportunities, outputs, runtime state, the real Method profile photo, or audit/test artifacts.
- Run clean-template portability and first-run acceptance tests from a copied location.

Exit: the production project and clean template expose the same portable workflow and canonical Method renderer.

## 12. Test and evaluation matrix

### Resume contract tests

- exact required locale IDs, class hierarchy, and section order;
- exact four-signal and four-expertise structure;
- responsibilities and achievements separated per recent role;
- conditional awards and earlier-career sections omit cleanly when empty;
- template CSS/JS/assets are copied from the versioned canonical source, not AI-authored;
- no inline scripts/styles or remote render assets;
- language switch updates active page, document language, and ARIA state;
- desktop, responsive, English print, Japanese print, and combined PDF screenshots;
- no browser header/footer, local path, clipping, blank page, or missing glyph;
- extracted resume text contains every expected content block in both languages;
- palette overrides meet contrast and cannot alter layout variables.

### Candidate migration tests

- strict-lint failure blocks migration;
- semantic-review or source change makes the fingerprint stale;
- unchanged PersonalWiki produces a no-op migration;
- migration changes no PersonalWiki file hash;
- ambiguous extraction cannot become assertion-grade confirmed content;
- migration failure preserves the prior candidate index;
- legacy embedded candidate facts migrate without being edited.

### Opportunity/research tests

- register directly from a valid folder;
- preserve user-written opportunity metadata;
- reject traversal and source/directory symlinks;
- capture exact source URL, excerpt, hash, and retrieval metadata;
- detect a research claim whose registered source does not support it;
- require disposition for every material job-description clause;
- prove research queries/logs contain no candidate facts or contact data;
- continue honestly with `research incomplete` when browsing is unavailable.

### Generation/validation tests

- full package with strong evidence;
- full package with real gaps and no invented answers;
- compatibility-only task without unrelated placeholder files;
- unsupported nonnumeric claim expansion;
- incomplete ledger coverage;
- proficiency qualifier loss;
- positive and negative inference from absent facts;
- Japanese strengthening or date precision loss;
- interrupted/concurrent task with rollback;
- complete manifest reproduction and stale-input rejection.

### Portability/template tests

- no machine-specific paths in code, config, templates, reports, or generated PDFs;
- copy project to a different location and run first-time setup;
- clean template contains no `JobDescriptions`/`Output` data files, candidate index, PII, real profile asset, or run logs;
- application uses only project-relative configured paths.

## 13. Acceptance criteria

The refinement is complete only when:

1. Generated HTML visually and structurally follows Method in both languages.
2. The resume schema cannot express the old generic arbitrary-section layout.
3. An opportunity agent cannot modify template HTML/CSS/JS during generation.
4. HTML works offline and uses no remote rendering assets.
5. PersonalWiki strict readiness is checked automatically.
6. Candidate migration is automatic, staged, atomic, reviewable afterward, and leaves PersonalWiki byte-identical.
7. Downstream tasks automatically detect and refresh stale candidate facts.
8. One natural-language registration request ingests and researches the opportunity with reproducible source capture.
9. Full-package and focused-task prompts work without terminal commands or intermediate approvals.
10. Missing experience appears as a gap/question and never as claimed experience.
11. Every material candidate claim has complete evidence and ledger coverage.
12. Every material job-description clause is extracted or explicitly dispositioned.
13. English and Japanese preserve the same facts, dates, numbers, qualifiers, and links.
14. Optional PDFs contain no local paths/browser furniture and pass rendered visual QA.
15. Run manifests cover every input, source, template, validation artifact, HTML asset, and PDF.
16. Security, privacy, interruption, and portability regression suites pass.
17. `InterviewWikiTemplate` passes a clean-copy first-run test with no personal or generated data.

## 14. Recommended review decisions

The user comments already settle the main product direction. The implementation can proceed with these recommended details unless changed during review:

- **Resume:** Method is the only production layout; palette values remain configurable within contrast limits, but structure and layout are fixed.
- **Reference handling:** keep `templates/Method/` frozen and promote a sanitized versioned production copy.
- **Candidate migration:** automatic and approval-free because it writes only InterviewWiki derived state; PersonalWiki remains immutable.
- **Freshness:** automatic fingerprint checks remove the need for users to remember when to rerun migration.
- **Opportunity setup:** registration, ingestion, and public research are one natural-language user action.
- **Generation:** missing evidence does not halt the whole package; it is surfaced and excluded from assertive content.
- **Focused tasks:** validate only the artifacts required by the requested task kind.
- **PDF:** HTML is mandatory; PDF generation remains optional and controlled by configuration/request.
- **Compatibility filename:** retain `Interview/candidate-analysis.md` for compatibility while changing its title/contract to Candidate Experience & Compatibility Audit.

No code, template, schema, workflow, or existing output has been changed by this planning step.
