# Provider recovery and shutdown audit

Date: 2 October 2026. Scope: InterviewSimulator and the personal installation, including the built-in browser and Google ADK Web. This report supplements the earlier durability validation; it records the failures reported after that validation.

## What caused the failures

| Reported problem | Evidence and cause | Change |
| --- | --- | --- |
| Ollama Test Model appeared to lose its connection | A validation exception escaped the probe endpoint and produced a plain HTTP 500 response. The browser tried to read it as JSON (a structured data format), then displayed the generic connection error. A Gemini reasoning setting could also carry over to Ollama; the selected cloud model did not declare support for that setting. | Validation failures now return safe structured errors. Provider/model changes reset reasoning to Provider default. Unsupported settings return a specific configuration error before dispatch. |
| Cloud model remained blocked | The nine-task qualification prompt allowed coaching prose that the application's stricter evidence validator rejected. Live testing reproduced this after correcting the reasoning setting. | The fictional coaching prompt now states the same clause and evidence rules as the validator. Validation remains strict; cloud models must still pass. |
| Long checks had no useful progress or stop control | The browser waited for a single long request. | Model checks run as cancellable jobs with progress, a Stop button, one active job, a ten-minute deadline, and a 45-second browser heartbeat timeout. Diagnostics exclude prompt content and credentials. |
| Interview setup could be changed mid-session | Setup navigation and the language selector remained accessible. | Language selection is on the landing page only and is frozen during a run. Connection, Models, Job, and the home link cannot leave an unfinished interview. Pause stays in the workspace; explicit cancellation unlocks setup. Model tests also lock navigation until stopped or completed. |
| Ctrl+C could wait for abandoned work | Server shutdown had no graceful deadline. A cancelled audio task could wait for its shielded subprocess thread until the native command's long timeout. | Both launchers have a five-second HTTP grace period. Shutdown cancels preparation, report, and model-check work. Native speech cancellation terminates and reaps owned child processes, escalating after two seconds if necessary. The llama.cpp launcher forwards termination to its owned server. |
| Gemini preparation returned 503 | Two latest saved preparation failures recorded `TEMPORARY_UNAVAILABLE`, HTTP 503, and dispatched requests. The record does not reveal Google's internal incident cause. | The interface recommends switching to a local model or another provider and retains saved work. Detailed codes remain in diagnostics. No automatic provider switch or additional consent is assumed. |

A **503** response means the provider was temporarily unable to handle the request, commonly because of overload or service unavailability. It does not by itself mean an invalid key or exhausted quota. **429** is the rate/quota category. This distinction follows [Google's Gemini troubleshooting documentation](https://ai.google.dev/gemini-api/docs/troubleshooting). The application cannot repair an upstream outage, and this audit does not claim that the reported Google model is currently available to every account.

For Ollama cloud models through `127.0.0.1:11434`, use `ollama signin` in a terminal first. Entering an API key in InterviewSimulator does not sign in that daemon (the background model server). Direct access to the official Ollama cloud uses its API key. See [Ollama cloud documentation](https://docs.ollama.com/cloud).

## Recovery users will see

- Choose the interface language on the Connection page before starting.
- Select the model, keep reasoning at **Provider default** unless supported, and run **Test model**. Ollama shows progress across nine fictional checks. **Stop model test** stops the local request; a remote provider may still bill work already received.
- During an interview, use **Pause interview** to pause within the workspace, or **Cancel interview** to unlock setup. Closing the browser cancels its active request work. Saved interviews require an explicit Resume after reload.
- If preparation fails because the AI service is unavailable, cancel the interview, change the provider/model, and start again. Native fixed questions remain an explicit option.
- If scoring fails, keep the saved answers, stop remaining report work, save a different model plan, and select **New assessment with current models**. Old assessment revisions remain separate.
- Ctrl+C stops the selected application server. A separately launched llama.cpp server or Ollama daemon must also be stopped separately when no longer needed.

## Validation

The regression tests cover structured error responses without secrets, provider recovery advice, model-check progress and cancellation, abandoned browser requests, preparation cancellation, native child-process cleanup, server leases, and history deletion that preserves Wiki inputs. Existing tests exercise ADK chat, durable answers, scoring/report recovery, voice controls, multilingual evidence rules, and provider boundaries.

Observed live checks:

- Ollama 0.33.2 with `gemma4:31b-cloud`: **9/9 qualification checks passed in 11.66 seconds** through the signed-in local daemon. A separate browser run also passed all nine checks and removed the model gate. These checks sent fictional text only.
- The model digest was `ef09f235533c96cd75e8deed88c628335cb69e2b3ce96275d0d7a67fe9887aba`. Results apply to that discovered model and its default reasoning setting.
- Browser acceptance: preparation and active-run setup lock, pause/resume, explicit cancellation and unlock, clean landing after reload, and English/Japanese/Traditional Chinese language selection.
- Real ADK Web factory: HTTP 200, app discovery, and orderly Ctrl+C exit in **0.46 seconds** with an isolated test agent.
- Real stalled HTTP request: SIGINT cancelled work, completed application cleanup, and exited in **5.29 seconds**.
- Native launcher regression: an owned child that ignored termination was killed and reaped.

Final validation results:

| Check | Result |
| --- | --- |
| Source installation, full Python suite | 162 passed |
| Personal installation, full Python suite | 162 passed |
| Ruff lint and formatting | Passed; 55 Python files formatted |
| Mypy static type checking | No issues in 33 source files |
| Browser state and voice regression scripts | Passed |
| JavaScript syntax and Git whitespace checks | Passed |

Both Python runs reported the same two dependency warnings: Starlette's TestClient/httpx deprecation and Pydantic's unsupported ReadOnly dictionary qualifier. Neither was a test failure. The audit did not change dependency versions.

## Deployment and requested cleanup

The source and personal installations contain identical copies of the 83 application, test, configuration, and documentation files in the deployment allowlist. Wiki content, environment files, credential settings, and Git metadata were excluded from deployment.

At the user's explicit request, the personal installation's 22 saved interviews, 22 simulation folders, four history database backups, translation cache, and ADK chat cache were cleared. All 18 interview-data tables are empty and both databases pass SQLite's integrity check. The Saved interviews endpoint returns an empty list. The registered job remains ready.

Before/after verification confirmed that 392 protected Wiki/settings/Git files and 16 model files were unchanged. Cleanup preserves database schema metadata and provider settings, so the app remains ready for a new practice session. No new backup containing deleted interview answers was created.

The built-in simulator, llama.cpp server/launcher, Ollama app/daemon, and temporary validation servers were stopped. No listeners remained on ports 8765, 8081, 8082, 9887, 9888, 9889, or 11434. The unrelated editor language server was left running. No Git commit or push was performed.

## Limits

The nine fictional tasks check format, language, evidence rules, and compatibility. They do not certify career-coaching quality for every interview. No new personal-profile cloud request or live Gemini billing test was needed for this repair. The existing Qwen 9B/4B preference is unchanged. Cancellation releases this app's resources and closes requests; an already-dispatched remote request may continue on the provider's servers.
