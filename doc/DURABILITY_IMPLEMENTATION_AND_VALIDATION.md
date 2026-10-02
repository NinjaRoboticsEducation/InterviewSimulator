# Durability, multilingual coaching and Ollama: implementation and validation

**Date:** 1 October 2026. **Status:** Implemented in InterviewSimulator and PersonalInterviewSimulator. This records the delivered changes from the [approved plan](DURABILITY_MULTILINGUAL_OLLAMA_REFINEMENT_PLAN.md), including the limits of the checks performed.

## What changed

| Area | Behavior now |
| --- | --- |
| Large profiles | Question planning selects a small set of complete, approved facts. It counts the rendered local prompt before generation. Confirmed answers are never silently shortened. |
| Preparation | A failed preparation remains available for retry. The user can choose ten native fixed questions with reduced personalization. No question is presented before preparation succeeds. Repeating the same preparation request does not create another interview. |
| Report recovery | Rate limits pause the report instead of triggering a cascade of failed requests. Safe error codes, retry times and task checkpoints are saved. Completed scores survive retries. The user can explicitly grant twelve more attempts or create a new assessment version with different saved models. |
| Validation | A received model response is distinguished from a successfully validated task. Invalid evidence, language, quantities, truncated output and unsupported coaching claims are rejected. Malformed localization JSON receives one bounded repair; provider quota failures do not trigger that repair. Repairs count against the attempt budget. |
| Report files | An export manifest, containing file checksums, becomes visible only after its report and data files are written. Uncommitted report files are ignored. Damaged exports can be repaired without overwriting earlier report files. New assessment versions do not display an older version as their current result. |
| Interview history | Browser startup opens a clean landing page. Saved interviews have explicit Resume, View history or View report actions. Cancelled interviews remain cancelled. ADK chats bind only to explicitly selected runs; a new chat does not adopt a recent interview. |
| Browser cleanup | Starting another run clears drafts, transcript state, audio resources, polling and pending requests. Late responses from an earlier run are ignored. Confirmation uses a translated page dialog. |
| Independent languages | The interface preference is separate from the saved interview language. Questions, recordings and reports continue to use the interview language when interface labels change. |
| Question localization | Complete questions are translated through an ADK task. Original evidence stays unchanged. Private, versioned caches include the model identity and question content. English paragraphs, placeholders and changed numbers are rejected. Written quantities such as “three”, “3”, 三つ and 三個 can remain equivalent. |
| Career coaching | Examples are finished answers, with evidence references for past claims and explicitly future wording for proposed approaches. Missing results cannot be inferred from performing a task. A separate model review checks the example and advice; rejected claims are not included as accepted coaching. |
| Ollama | Native text API support for loopback servers on this computer and the official cloud destination. Connection profiles bind credentials to a fixed destination. Cloud aliases on local daemons require cloud consent. Nine fictional compatibility checks include unsupported-claim rejection; a failed recheck revokes qualification. Runtime checks reject changed model locality and incompatible thinking settings. |
| Local configuration | `local-server --context-tokens 8192` permits an explicit larger working context; supported values are 4096–16384. The default remains 4096. Identical GGUF files in the two copies can share a server after fingerprint verification. |
| Public source | An allowlist release builder excludes candidate data, job output, keys, model files, databases, debugging prompts and raw benchmark records. Small fictional fixtures and automated tests remain included. |

A **checkpoint** is a saved task-progress record. A **checksum** is a file fingerprint used to detect an incomplete or changed export. **GGUF** is the local model file format. **JSON schema** defines the shape of a model response. ADK is Google's Agent Development Kit; the framework remains pinned to **2.10.0**, including its Agent, Workflow, Runner and session services.

Question-bank adaptation remains bounded reuse and selection within the same job and approved evidence. It does not train or fine-tune model weights. Existing manual PersonalWiki and InterviewWiki workflows remain prerequisites.

## Validation performed

The final automated suite has **145 tests**, including 39 new corpus and localization/release checks. All three environments passed:

| Environment | Tests | Elapsed time |
| --- | ---: | ---: |
| InterviewSimulator | 145 passed, 2 dependency warnings | 44.26 s |
| PersonalInterviewSimulator | 145 passed, 2 dependency warnings | 47.00 s |
| Fresh clean-release installation | 145 passed, 2 dependency warnings | 34.34 s |

Ruff lint and formatting passed for **52 Python files**. Mypy, including untyped function bodies, passed for **31 source files**. JavaScript syntax checks, both browser regression scripts and `git diff --check` passed. The personal copy also passed its own lint, formatting, type and browser checks. These checks use the project's locked environment.

Coverage includes real ADK interview pauses and resumptions, two-chat isolation, cancelled-history handling, request replay, frozen scoring, answer edits, concurrent migration and backups, rate-limit recovery, report revisions, export damage and orphan files, exact answer spans, multilingual validation, copied model fingerprints, destination restrictions, credential redaction, Ollama native requests, locality changes and qualification failure.

The built-in browser was exercised with an isolated fictional profile, real ADK interview flow and a stub assessor. Checks covered:

- Cancellation followed by reload: a clean landing page and a cancelled history entry, without a Resume button.
- Failed Japanese and Chinese preparation followed by explicit native-deck recovery.
- Pause, reload and explicit Resume at the same question.
- All nine combinations of interface language and interview language, with unchanged question content.
- Ten confirmed answers and a complete formatted report.

This browser check does not establish model-scoring accuracy or physical microphone quality. Local model checks below use the actual language models separately.

The [fictional language corpus](../tests/fixtures/multilingual_intents.json) has **30 distinct intents**, six per question category, with English, Japanese and Traditional Chinese versions. Its source locale rotates across all three languages. It covers professional terms, uncertainty, negation, dates, quantities, team ownership and missing evidence. Regression checks exercise all **270 source/target combinations**, preserve protected names and quantities, and reject changed metrics and unfinished placeholders. These checks validate the reference text and application guards; they do not mean a model generated or passed all 270 translations. The corpus is explicitly marked **awaiting native review**.

For language qualification, a native reviewer should compare each generated question with its source and referenced evidence, rate meaning and naturalness separately from 1 to 5, and flag any changed ownership, uncertainty, negation, name or quantity. The approved gate requires an average of at least 4/5 and no critical meaning error. A model's self-review does not replace this step.

The clean release was installed with `uv sync --locked` into a new environment. The first offline attempt correctly reported an uncached dependency; the locked online installation then succeeded. ADK Web started from that installation, listed `interview_practice`, and served its interface with HTTP 200 after its normal local redirect. Its in-memory chat session warnings are expected: the simulator's interview records are stored separately, and explicit Resume reconnects to them.

The personal copy's homepage, settings and speech endpoints returned HTTP 200; requests with an invalid local token returned HTTP 403. Its own imports, own model path and one prepared job were verified. No real interview was started or rescored during these checks.

Two dependency warnings remain in the test suite: the Starlette/httpx test-client deprecation and a Pydantic warning about a dependency's `ReadOnly` typing qualifier. Tests pass despite these warnings; answer locking is enforced in the simulator's database transactions.

## Local model observations

Reference: the user's 2018 Intel Mac mini, six-core i5, 32 GB RAM; llama.cpp **b10621**, CPU inference with six threads and a 4096-token context, Qwen3.5 Q4_K_M, thinking disabled, temperature 0.2. Exact model filenames and SHA-256 digests are in the [download manifest](../config/download-manifest.json). Qualification tasks requested at most 1200 assessment tokens and 2048 coaching tokens, reduced only when needed by the complete-prompt budget check. Tasks used fictional team-project evidence that explicitly said the candidate **did not lead** the projects. The preparation fixture contained 67 facts.

| Check | 9B | 4B |
| --- | --- | --- |
| Large-profile planning | Passed | Initial invalid self-introduction evidence selection rejected; final planning/repair check passed |
| Japanese and Traditional Chinese translation | Passed | Passed |
| Assessment in all three languages | Passed | Passed |
| Finished coaching in all three languages | Passed after fixing sparse-evidence instructions and number equivalence | English and Chinese passed; final Japanese check passed after accepting valid future wording |
| Unsupported outcomes or leadership claims | Rejected during the initial checks | Rejected during the initial checks |
| Final stricter advice review | English assessment and coaching passed | Japanese assessment and coaching passed |

Selected observed task durations:

| Model | Language | Assessment | Coaching, including evidence review |
| --- | --- | ---: | ---: |
| 9B | English, final stricter review | 80.93 s | 116.33 s |
| 9B | Japanese | 73.42 s | 109.18 s |
| 9B | Traditional Chinese | 79.92 s | 102.48 s |
| 4B | English | 47.10 s | 52.01 s |
| 4B | Japanese, final stricter review | 42.86 s | 78.39 s |
| 4B | Traditional Chinese | 56.29 s | 120.47 s |

The final 4B large-profile planning check took 68.04 seconds; Japanese translation took 8.87 seconds. Initial loading/fingerprinting is excluded from those final 4B task timings. The first 9B coaching check included cold file fingerprinting and is excluded from this table.

These are individual qualification samples, not controlled idle-machine benchmarks: installation, import and regression work ran during parts of the measurements. Some table entries predate the stricter advice audit; the final checks are identified explicitly. Output length and repairs affect duration, so this table does not prove a fixed speed ratio or multilingual score fairness. A full ten-answer local report can take many minutes on this Intel CPU. Questions and local speech are handled separately from final scoring.

Keep **9B Q4_K_M as the requested quality-first default**, with **4B Q4_K_M as an explicit alternative**. Failed validation produces an incomplete report with recovery controls; the application never accepts an invented achievement merely to finish a report. Model review is another useful check, not proof of factual truth. Users should verify examples against their real experience before using them.

## Personal data and deployment

Before deployment, consistent SQLite backups were made under the personal copy's `.simulator/maintenance/` folder, under the exclusive server lock. Overwritten source files were backed up there too. Database schema version 3 has its own pre-migration backup.

Verification preserved:

- All **14** saved interviews: **6 answered and 8 cancelled**.
- Exact saved answers and evaluation payloads.
- All **144 ADK sessions and 415 events**.
- Checksums of **203 protected files**, including existing reports, wiki inputs/output, `.env`, private settings and the Git index.
- Model file sizes and modification times.

Only application-owned source, tests, scripts, public configuration templates, documentation and lockfiles were synchronized. **79 common files** match across the two application copies. Private wiki content and nested Git metadata were excluded. Each virtual environment was synchronized in its own directory.

The release builder selects **241 source files**, including the fictional corpus and its regression tests. Their checksums are verified. A regression test proves that fictional private-data canaries in runtime settings, job output, `.env` and debugging prompts are excluded. The reviewed release content contained no private-data paths or matches for the credential/local-path patterns checked. **222 distinct Git-history blobs** were scanned for common provider-key and private-key patterns, with no matches. Pattern scanning is a useful release check, not proof that every conceivable secret can be detected. Nothing was committed or pushed during this implementation task.

## Remaining qualification limits

The functional implementation, automated regression checks and safe synchronization are complete. **The approved plan's full language and device quality qualification is incomplete.** The limits below are outstanding checks, not passing acceptance results.

| Check | What is still unverified |
| --- | --- |
| Live Ollama daemon and official cloud | Native contracts, locality and gates are tested with HTTP fixtures. No Ollama service or account was available for live qualification. Cloud models stay gated by the application's representative test. |
| Paid cloud report generation | No candidate data or account keys were sent to a cloud provider. Google/OpenAI/Anthropic requests, typed errors and recovery were tested with controlled responses. |
| Native-language review | The 30-intent reference corpus and automated guards pass; small live model samples pass. Native review of generated translations, semantic fidelity and score calibration remains incomplete. |
| Full model/report acceptance | The browser completed a ten-answer fictional report with a stub assessor. Actual 9B/4B checks covered individual tasks in each locale, not six complete ten-answer reports. Repeated idle-machine timing, memory measurements and cold/warm full-report comparisons remain unverified. |
| Physical microphone and accents | Browser recording lifecycle tests passed; an actual person speaking through the browser microphone still needs a device check. Earlier synthetic local speech checks are retained in the historical validation record. |
| Windows, Linux, Apple Silicon and GPU performance | Portable code and CI configuration are included, but those physical devices were not available for execution here. |
| OS credential vault behavior | Safe-backend policy and copied identities are tested. Real account lock/unlock and permission-denial behavior remains device-dependent. |

Application and temporary validation servers are stopped after testing: ports 8765, 9888, 9889 and the temporary 4B port 8082 were confirmed closed. The pre-existing 9B llama.cpp server on port 8081 is left untouched. Follow the [README](../README.md) to start either interface; run one interface per project copy at a time.
