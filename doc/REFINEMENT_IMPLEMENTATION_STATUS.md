# Earlier refinement implementation and validation

**Historical record:** The current durability, multilingual coaching and Ollama changes supersede several behaviors below. See [current validation](DURABILITY_IMPLEMENTATION_AND_VALIDATION.md).

Date: **1 October 2026**, Japan time. This records the implementation of the user-approved [refinement plan](REFINEMENT_RESEARCH_AND_IMPLEMENTATION_PLAN.md). The earlier plan remains the design and research record; this document records what was built and what was actually tested.

## What is implemented

| Area | Delivered behavior |
|---|---|
| Setup | Four installation profiles, shell and PowerShell entry points, common Python installer, pinned model downloads and checksums, resumable downloads, preserved `.env`, native-tool guidance, and an installation receipt. |
| Text providers | Local llama.cpp plus Google, OpenAI, and Anthropic text adapters through Google ADK. Model lists come from the account's API. Unknown models require a synthetic structured-output probe. Question preparation, assessment, coaching, and summary have separate model settings. |
| Credentials | New keys stay in server memory unless native OS vault storage is selected. Plaintext vault backends are rejected. Copy/device-specific namespaces, thread-safe access, serialized namespace creation, disconnect/reconnect/forget controls, and secret-safe validation errors are included. |
| Guided browser | Modern Minimalist theme; connection, models, job/readiness, interview, answer review, and report screens; responsive layout; keyboard focus; English, Japanese, and Traditional Chinese interface labels. Some technical status messages remain English. |
| Interview state | Durable ADK turns, confirmed-answer versions, stale-tab rejection, pause/resume/cancel/restart, read-only history, and editing before scoring. Editing never changes already selected later questions. Scoring atomically locks the final snapshot. |
| Questions and learning | Ten topic-balanced questions; optional grounded variants; a bank of acknowledged questions for the same job and current evidence; bounded adaptive selection with Japanese/Chinese character matching. This is reuse and selection, not model training. |
| Coaching | Separate task model, approved fact references, four-part examples assembled from exact profile statements, placeholders for missing evidence, practical suggestions, and rejection of recognizable schema-instruction echoes. Suggestions are explicitly distinguished from verified career facts. |
| Reports | Escaped Markdown, sanitized HTML, score cards, topic and rubric bars, highlighted feedback, Markdown/HTML downloads, print styling, retained report revisions, model identities and call receipts. Partial work is labeled and saved scores are reused on retry. |
| Local voice | macOS installed voices, Windows System.Speech adapter, configurable Piper and Japanese Open JTalk, local whisper.cpp transcription, Traditional Chinese conversion, bounded recordings, microphone/audio cancellation, and typed fallback. |
| Recovery | Serialized database migration with a pre-migration SQLite backup, immutable scoring snapshot, bounded logical model attempts, interrupted-call records, incremental saved results, and exclusive server leases. |

The implementation keeps the existing manual PersonalWiki and InterviewWiki workflows. It does not build or alter your career claims or job packages automatically. Google ADK remains pinned to **2.10.0** in the lockfile; cloud tasks use an ADK `BaseLlm` adapter and ADK `Agent`/`Runner`, while ordinary Python controls validation and storage.

## Automated and browser validation

The final suite contains **79 tests**. Both copies are validated using `python -m pytest`, which ensures the tests use that copy’s interpreter. Final execution results:

| Check | Result |
|---|---|
| Original project, rebuilt interpreter | **79 passed**, two dependency warnings, 277.29 seconds |
| Personal copy, rebuilt interpreter | **79 passed**, two dependency warnings, 234.26 seconds |
| Ruff lint and format | Passed in both copies; 45 Python files checked |
| Mypy source types | Passed; 27 source files |
| JavaScript syntax and two browser regression scripts | Passed |
| Documentation links and Git whitespace check | Passed |

The longer rebuilt-environment test times include first imports and external-drive I/O; they are not inference timings. Earlier warm-environment suites completed sooner. The two dependency warnings are described below.

The tests cover real ADK interview turns and ADK chat commands; answer edits, versions and revision conflicts; frozen scoring; two-chat association; migration backup and concurrency; question grounding and Japanese/Chinese matching; all three provider request/response contracts; secret exclusion and redacted errors; malformed model catalogs; native-vault policy and copied identities; retry and attempt budgets; local token-context preflight; safe report rendering; installer download recovery; local voice adapter command boundaries; and report cancellation/recovery.

A complete synthetic cloud-configured interview exercised **22 ADK model tasks**: question preparation, ten assessments, ten coaching responses, and summary. It verified report export and a retry that made no additional model calls. Provider HTTP responses were controlled test fixtures; this was **not a paid live-provider test**.

Browser checks used a synthetic company and profile with the real ADK interview state machine and a stub assessor. Verified actions included onboarding, job selection, confirming a first answer, previous-question editing, review, pause/resume at the same question, completing ten answers, formatted reports, and locked history after scoring. Desktop and a **390 × 844** viewport were inspected; the small viewport had no horizontal overflow. JavaScript regression checks also cover answer retry identity, stale report polls, audio failure, microphone cancellation, transcription cancellation, and recording cleanup. These checks do not represent a human microphone test.

Ruff checks Python style and formatting. Mypy checks source types. JavaScript syntax and both browser-state test scripts are checked separately. Two dependency warnings remain: Starlette's HTTP test-client deprecation and a Pydantic warning about a dependency's `ReadOnly` typing qualifier. They do not cause test failures; the application does not rely on that qualifier for answer immutability.

## Environment repair and installer validation

The personal copy contained console scripts pointing to the original project, and the root activation scripts still referred to an older wiki template. Synchronizing an existing copied environment alone did not repair all of those paths. The installer now checks environment origin, retains misplaced environments under `.simulator/environment-backups/`, recreates them, and records their project/OS/processor identity. A regression test verifies that private `.env` content survives this repair.

The installer was executed with **`local-voice --skip-models` on both project copies**, then the development group was synchronized. This exercised all three Python projects while preserving settings and existing model files. It does not establish fresh model-download or native compiler installation on a clean operating system. The root environment rebuild compiled `cryptography==50.0.1` successfully on Intel Mac; this lock has no Intel Mac wheel. The README now names Apple's development tools, Rust and OpenSSL as build prerequisites. The supported [cryptography build instructions](https://cryptography.io/en/latest/installation/#building-cryptography-on-macos) explain why these are needed.

Interpreter checks confirmed that the personal copy imports both the simulator and InterviewWiki from its own folder, its GGUF is inside that copy, and its local speech readiness check passes. Ctrl+C shutdown of the ADK wrapper is handled without an application traceback.

## Measured local models

Reference device: 2018 Intel Mac mini, six-core 3 GHz i5, 32 GB RAM, macOS Sequoia 15.7.9. Local server: llama.cpp **b10621**, CPU, six threads, 4,096-token context; Qwen3.5 Q4_K_M; thinking disabled; temperature 0.2. Output allowances: 1,024 assessment tokens and 2,048 coaching tokens, subject to a context preflight. The preflight uses the server's actual tokenizer and rejects oversized inputs instead of silently cutting a confirmed answer.

These are one synthetic answer per language, with one confirmed profile fact and missing adoption numbers. They are **small samples, not production latency guarantees or scoring calibration**. Initial model fingerprinting took about 12 seconds for 9B; table timings are assessment and coaching calls. Some lightweight checks ran alongside model tests, so these are not controlled idle-machine measurements.

| Model | Language | Assessment | Coaching | Combined | Practice score |
|---|---|---:|---:|---:|---:|
| 9B | English | 67.51 s | 87.29 s | 154.80 s | 58.8 |
| 9B | Japanese | 61.99 s | 102.23 s | 164.22 s | 56.2 |
| 9B | Traditional Chinese | 55.53 s | 121.43 s | 176.96 s | 70.0 |
| 4B | English | 47.50 s | 47.48 s | 94.98 s | 51.2 |
| 4B | Japanese | 39.64 s | 64.88 s | 104.52 s | 56.2 |
| 4B | Traditional Chinese | 33.45 s | 49.16 s | 82.61 s | 51.2 |

Raw synthetic records are retained privately and excluded from the public release. Earlier baseline runs are retained separately. The grounding check was corrected to accept both ASCII and full-width placeholder brackets, using the saved examples without changing timings.

All six initial examples used approved statements and verification placeholders, and exact-quote checks passed. However, the first 9B Chinese coaching output repeated schema instructions; the final validator now rejects that recognizable echo and allows one recorded repair. A fresh 9B Chinese guard check passed: assessment **73.82 s**, coaching **86.40 s**, total **160.22 s**, score **51.2**. The first Chinese output above is historical evidence, not an output accepted under the final guard.

The changed score for a roughly equivalent repeated case, and differences between languages, show that **fairness and repeatability are not established**. The Japanese 9B advice also inferred an absence of users from unverified user counts. Exact-fact examples prevent that claim entering the example answer, but a schema validator cannot prove every free-form suggestion is true. Reports explain that suggestions must be checked against real experience. No human quality panel, hiring-outcome prediction, or calibrated qualification score is claimed.

Keep **9B as the requested quality-first default** and **4B as an explicit speed alternative**. The samples do not establish that 9B is universally better. Ten similarly sized assessment/coaching pairs could take roughly 14–30 minutes on this Intel CPU; this is an extrapolation, not a measured complete local report. Prepared questions remain available immediately; expensive scoring happens afterward and shows saved progress.

## Measured local speech

Installed Mac voices generated synthetic questions; FFmpeg produced WAV audio and multilingual whisper.cpp small recognized it. All three passed. Raw records are retained privately.

| Language | Audio length | Speech generation | Recognition | Result |
|---|---:|---:|---:|---|
| English | 4.41 s | 1.61 s | 7.83 s | Expected words recognized; punctuation changed |
| Japanese | 4.98 s | 1.26 s | 4.04 s | Expected words recognized; punctuation changed |
| Mandarin / Traditional Chinese | 3.96 s | 0.91 s | 4.35 s | Expected words recognized; Traditional Chinese output |

The same three-language playback/transcription check also passed in the personal copy after environment recreation, using its own local model. Raw personal-copy records are retained privately.

These measurements use generated speech, not a person speaking through the browser microphone. Users should still verify their actual microphone, permissions, accent, room noise, and selected voices using the README steps.

## Qualification limits and deployment

| Check | Status |
|---|---|
| Reference Mac Python/ADK, local models, synthetic speech | Executed locally |
| Built-in browser layout and synthetic interview | Executed locally |
| Google/OpenAI/Anthropic contracts and secret-handling tests | Tested with controlled HTTP fixtures; no account keys used |
| Live cloud model discovery, billing, model behavior | Not executed; no provider keys supplied. A synthetic probe is required for unknown models, and real interview quality still needs review. |
| Actual native vault lock/unlock/denied-access behavior | Policy and backend behavior tested with fixtures; native account qualification remains open |
| Physical browser microphone and human speech | User check remains necessary |
| Windows/Linux native voices and installation | Adapters and boundaries tested with fixtures; physical devices not available |
| Installer environment setup | Executed on both existing copies with environments recreated as needed and model downloads skipped; cloud-text dry run passed |
| Fresh native inference builds / all profiles on clean OS installations | Not fully qualified; supported routes and prerequisite checks are documented |
| Apple Silicon / GPU acceleration | Not measured here; CPU is the default |
| Multilingual score fairness and coach accuracy | Not calibrated; model advice requires verification |

Source deployment updates only application code, tests, configuration templates/manifests, lockfiles, scripts, and documentation. The personal copy's `.env`, PersonalWiki, InterviewWiki jobs/output, models, databases, and existing reports are preserved. Overwritten source files are backed up before transfer; database upgrades make their own SQLite backup. Virtual environments are recreated/synchronized in place rather than copied.

Live smoke checks returned HTTP 200 for the personal homepage, settings and speech endpoints, found its one registered job ready, and rejected a request without the local token with HTTP 403. No real answer was submitted. The final ADK Web startup listed `interview_practice`, then exited with code 0 on interruption without a traceback.

Source backups are retained under each copy’s `.simulator/source-backups/`; copied environments are under `.simulator/environment-backups/`. The personal source transfer covered 50 changed files, with four subsequent shutdown/portability fixes and final documentation updates. Private settings remained unchanged.

The built-in, preview, and temporary model servers are stopped at completion. Follow the [README](../README.md) to start the interface you want. Use one interface at a time.
