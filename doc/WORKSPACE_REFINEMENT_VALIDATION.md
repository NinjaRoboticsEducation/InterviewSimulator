# Workspace and mandatory-example refinement validation

Implementation date: 2 October 2026.

This implements the approved [workspace, recording, and example plan](WORKSPACE_RECORDING_AND_MANDATORY_EXAMPLES_PLAN.md), including the visible 6,000-character reminder and model-provider setup guidance.

## What changed

- The six steps now read Get started, Select Model, Select Job Interview, Start Interview, Review your answers, and Interview report. Japanese and Traditional Chinese labels and introductions are included.
- Get started contains the introduction and interface-language choice. Provider setup is on Select Model, with one main model selector and concise provider-specific guidance. Local instructions show the recommended Qwen3.5-9B Q4_K_M settings in `.env`, followed by the terminal command.
- Saved interviews appear on Interview report. Cancelled runs are hidden without deleting history. Printed reports omit the saved-interview list.
- Each recording has a three-minute countdown. Extend recording repeatedly appends to the edited answer; Record answer replaces it after successful transcription. Failed transcription preserves the draft. Over-limit text remains available to shorten before confirming. The server also caps delayed browser recordings at three minutes and returns a notice.
- The answer limit is 6,000 Unicode characters, with a visible reminder and count. Original recognition is separate from the corrected combined answer; later edits retain the initial recognition record.
- The two advanced recovery buttons are removed from the web interface. ADK commands remain; `report-allowance` and `report-revision` provide terminal access under the installation lock, with explicit confirmation and cloud consent where needed.
- Every newly finalized report requires ten valid examples, including skipped answers. Missing examples keep the report a clearly labelled draft. Resume processes missing examples without changing completed scores. Markdown and HTML exports identify drafts; prior reports are not regenerated.

## Example-answer root cause and safeguards

The old validator treated all nonhistorical wording as future plans and demanded a narrow set of future-expression keywords. Natural motivation and interviewer-question wording could therefore fail despite containing no invented career claims. Company facts also needed their own evidence scope.

The new contract separates candidate history, company/job facts, proposed approaches, suggested motivations, questions for the interviewer, and connecting wording. Candidate achievements still require confirmed candidate evidence. Company statements use separate source references. A model-based evidence review checks all clauses, including unsupported claims hidden inside an intent or question. Proposed numeric targets must remain clearly future, not claimed accomplishments. The repair receives the failed clause and a safe reason when available, and is limited to one repair attempt. Validation failure never becomes a fabricated example or a final report.

Ollama qualification is versioned again and includes natural motivation wording in all three languages. Previously qualified Ollama models need the updated test.

## Validation

- Source and personal installations: 176 Python tests passed in each, including ADK integration, report durability, all three languages, skipped-question examples, resume without rescoring, safe evidence validation, terminal recovery, and recording limits.
- Both JavaScript suites passed: navigation and language locks, cancelled history, stale-response handling, repeated recording extensions, replacement, countdown expiry, Unicode counting, overflow preservation, and failed transcription.
- Ruff lint and formatting checks passed. Mypy found no issues in 34 application source files. Git whitespace checks passed.
- Browser checks used an isolated fictional opportunity: landing introduction, provider/model page, local command guidance, locked interview navigation, answer counter and Extend availability, cancellation filtering, history placement, and translated navigation in English, Japanese, and Traditional Chinese.
- A clean release was built from the allowlist and checked to exclude environment secrets, personal state, wiki content, generated interviews, model binaries, and database files. Automated tests use fictional fixtures.

Two dependency warnings remain: Starlette's HTTPX test-client deprecation and Pydantic's handling of a dependency's ReadOnly annotation. Neither caused a failed test.

## Limits of this validation

Recording timing and failure handling were tested with simulated browser audio and synthetic waveform files. This pass did not record a physical microphone or run live cloud/model quality benchmarks. An evidence-review model can still make mistakes; users should verify example answers before using them. Provider outages and exhausted quotas cannot be prevented, and unfinished reports remain resumable drafts.

## Deployment and shutdown

Application and documentation files are synchronized to PersonalInterviewSimulator. Private wiki content, saved interviews and reports, environment settings, provider configuration, and the existing Git index are preserved. The final check covered 15,800 protected files. All content hashes matched except SQLite transaction-counter header bytes: restoring those bytes in memory reproduced the original database hash exactly, and its integrity check passed. No interview rows changed. All 87 application/documentation/fixture files match across the copies. Replaced code has a local backup under the personal installation's `.simulator/maintenance` directory. No Git commit or push was performed.

The personal interview server, llama.cpp launcher/server, and temporary preview were stopped. Their ports (8765, 8081, and 9890) were verified closed. Restart explicitly when ready to practise.
