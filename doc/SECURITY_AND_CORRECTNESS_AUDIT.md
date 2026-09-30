# Interview Simulator audit

30 September 2026

The findings below describe the original audit and its fixes. A later implementation follow-up is recorded near the end of this document. Automated checks cannot establish that model judgments are fair or that every device is qualified.

## What was reviewed

The review compared the approved implementation plan with every application source module under `src/interview_simulator`, the browser JavaScript, dependency configuration, tests, and the InterviewWiki integration boundary. Serena MCP symbol inspection and reference navigation were used for the engine, storage, ADK execution, and evaluation code, alongside full source reads and regression tests. Context7 MCP was used to check Starlette request handling: an allowed Host header is not an Origin check, and upload limits must apply before multipart parsing. This was a source-level audit, not an automated claim that Serena proves code secure.

The nested InterviewWiki regression suite was also run. This was not a line-by-line audit of every third-party dependency, the whole PersonalWiki codebase, native audio binaries, or downloaded model weights. Existing unrelated repository changes were preserved. No personal source records or real interview packages were rewritten.

The supported boundary is one local user, one server process, one active interview, and a browser on the same device. Operating-system account compromise and a hostile process already running as that user remain outside that boundary.

## Findings and fixes

Severity here describes impact within that local deployment, not a formal CVSS score.

| Finding | Severity | Correction | Main verification |
|---|---|---|---|
| Host checking alone did not protect browser API operations from hostile websites. | High | Check Origin and Fetch Metadata, require a random per-process request token on all API routes, disable framing, and prevent caching. Static JavaScript replaces inline scripts so the content policy can restrict executable scripts. | Missing token and hostile Origin rejected; authenticated local requests and static assets work. |
| Upload size was checked after multipart parsing; text requests were unbounded. | High | Count request bytes before parsing, including chunked requests; apply a 30-second upload deadline, 20 MB audio limit and 6,000-character answer/transcript limits. | Oversized declared and streamed bodies rejected before the downstream parser. |
| Sensitive and unreviewed candidate facts could shape questions or be sent to the model. | High | Retain only facts explicitly marked confirmed and non-sensitive for the candidate snapshot; repeat eligibility checks for question construction and model inputs, including older runs. | Sensitive and draft facts excluded from generated questions. Existing complete snapshots are not retroactively scrubbed. |
| Concurrent state requests could resume the same ADK pause twice. | High | Serialize reconciliation and run creation; use transactional database writes and a server-process file lease. Expose the active run so a browser can recover even after losing local storage. | Four concurrent recovery requests reach exactly question two; a second server lease is rejected. |
| A crash or cancellation during coaching could discard a completed assessment. | High | Persist the assessment before coaching; allow coaching/error fields to be added without changing scores. Shutdown cancels and awaits background tasks. | Cancelled coaching preserves the first score; retry assesses each of ten answers only once. |
| Model HTTP clients could inherit environment proxies or follow redirects. | High | Use an explicit no-proxy, no-redirect HTTP client through ADK/LiteLLM; require a numeric loopback URL, disable retries, and bound execution time. Health checks also ignore proxies and redirects. | Real pinned ADK/LiteLLM execution through a mock HTTP transport reaches only the configured local completion endpoint. Remote and hostname endpoints are rejected. |
| Private state and report paths lacked consistent symlink and permission checks. | High | Reject symbolic links for simulator paths and SQLite sidecars; apply owner-only directory/file permissions on POSIX; recheck before report reads and database connections. | Symlink database/report refusal; private permission checks. Windows account permissions still need device qualification. |
| Snapshot capture could accept a file changed between validation and reading. | Medium | Validate again after capture, compare source hashes, and compare the persisted snapshot to the database before resuming or reporting. Restore a missing snapshot from saved state. | Changed run snapshot rejected; missing snapshot restored; read-only preflight tests pass. |
| Native audio jobs blocked the event loop; long recordings were silently truncated. | Medium | Run bounded native work in a thread, serialize it with model work, and reject decoded recordings over three minutes. Keep the CPU slot until cancelled native work actually ends. | Long recordings rejected before speech recognition; subprocesses retain explicit deadlines. |
| Untrusted audio formats and speech text had unnecessary interpreter exposure. | Medium | Restrict decoder formats/protocols, pass macOS speech text through standard input, and flatten Piper input lines. | Decoder allowlist verified; option-like speech text stays on stdin. This does not substitute for keeping native decoders updated. |
| Browser retries and overlapping recording/playback/report actions could affect the wrong turn. | Medium | Preserve an immutable submission payload for retry, lock conflicting controls, bind transcription to the original turn, and ignore stale report polls. | Node browser-state harness verifies identical retries, restored report locking, and stale-poll isolation. |
| A role question could be graded against a different requirement from the one in its wording. | Medium | Bind the selected requirement to both question wording and assessment input. | Multi-requirement regression fixture. |
| Report revision counting and lexical sorting could select or overwrite the wrong report. | Medium | Use numeric revision ordering and the greatest existing revision plus one; reuse identical reports. | Revision 12 is selected and a changed report becomes revision 13; identical report generation is idempotent. |
| Untrusted Markdown content could introduce active images, links, or HTML into an exported report. | Medium | Escape Markdown metacharacters and HTML; the browser uses text content for reports. | Active-content escaping regression. |
| The manifest's model field could imply the current alias generated earlier saved scores. | Medium | Label it explicitly as configuration at export, not proof of the loaded model or past assessments. | Source review; full per-answer model/prompt provenance remains a release gate below. |
| The development pytest version had a published temporary-directory vulnerability. | Medium | Update the project constraint and lockfile to pytest 9.1.1, above the advisory's fixed version. | Repeat dependency audit and test suites. Advisory: `PYSEC-2026-1845` / `GHSA-6w46-j5rx-g56g` / `CVE-2025-71176`. |

## Verification results

- Simulator: **37 tests passed**, including actual pinned ADK graph/session behavior and the new security/recovery regressions.
- InterviewWiki: **25 tests passed**, using the updated parent environment.
- Ruff lint and formatting checks passed; mypy passed for all 16 Python source files.
- JavaScript syntax and the deterministic browser-state harness passed.
- Locked dependency installation succeeded. `pip-audit` reported **no known vulnerabilities** after the pytest update for packages it could audit. The two local editable projects, `interview-simulator` and `interviewwiki`, are not published packages and were skipped by the advisory service; they were reviewed as local source instead. Advisory scans cannot detect unknown vulnerabilities or assess model/native assets.
- Two upstream warnings remain: Starlette's TestClient deprecates its httpx integration, and Pydantic notes that a dependency's TypedDict read-only annotation does not enforce mutation protection. Neither failed the tests.

The HTTP transport check uses synthetic data and an in-memory transport. Audio safety checks use controlled subprocess fixtures. The browser-state harness is not a real microphone/browser compatibility test. Earlier model and speech measurements remain in the implementation status document; this audit did not repeat a complete live-model interview.

## Follow-up implementation status (30 September 2026)

The user requested the remaining software work and a working ADK Web chat. The changes below have been implemented after the original 37-test audit. The original findings table remains a record of the initial review.

| Original open item | Current implementation |
|---|---|
| Per-answer model and prompt provenance | New assessments and coaching calls check llama.cpp `/props` against the configured GGUF file, hash the local file, record prompt hash/version and invocation ID, and reject a model change within one assessment or between new scores. Earlier reports lacking this metadata remain historical; they cannot be retroactively attested. |
| Coaching claim safety | The report example uses exact confirmed, non-sensitive PersonalWiki fact text with placeholders. The coach's free-form explanation and next steps are replaced by localized, controlled guidance. Model-selected fact IDs are checked. Usefulness and scoring fairness still require human review. |
| Adaptive interview code | A bounded deterministic selector chooses current-evidence bank variants within the planned topic slots, saves the decision before ADK advances, and uses the fixed question on a tie or empty bank. Both interfaces accept the mode. Cold-start runs explain their fixed fallback. This is an implemented limited adaptive policy; broader learning quality and user qualification are still open. |
| Backup, restore, and selective deletion | Stopped-server CLI commands export SQLite-consistent databases and run files into a checksummed ZIP, verify hashes/SQLite on restore, refuse existing data and unsafe paths, and remove a selected run with its ADK session and derived bank links. Backups are unencrypted and need private storage. |
| Report publication | Versioned report and run exports are written before an atomic manifest pointer. `verify-run` checks the current manifest's hashes. A crash can leave an unused new file; the previous verified report remains available. |
| Google ADK Web interface | `agents/interview_practice` is an ADK `BaseAgent` backed by the same interview engine; `serve-adk` starts ADK Web under the one-process lease with temporary ADK Web chat storage, preventing a second durable transcript outside the simulator backup/delete boundary. A real ADK Runner test covers job commands and ten turns. Live localhost ADK Web startup returned `interview_practice` from `/list-apps`. Voice practice is in the built-in browser. |

The original validation counts above apply to the first audit. The follow-up test run passed **45 simulator tests and 25 InterviewWiki tests**, covering the new ADK chat, adaptive replay, provenance, backup/restore/delete, and report verification. Lint, formatting, typing, JavaScript syntax and browser-state checks passed. Both localhost servers started; ADK Web listed `interview_practice`, and the built-in page and authenticated job API returned HTTP 200. No real prepared opportunity was available in the job picker. See the current README for commands and supported behavior.

### Checks that require people or other devices

1. **Real opportunity acceptance:** no prepared real job and reviewed candidate facts were supplied for an end-to-end live interview. Synthetic fixtures cannot establish whether a real report is professionally fair.
2. **Language and coaching review:** native speakers and a career specialist should review ten-answer examples and feedback in English, Japanese, and Traditional Chinese. Deterministic guardrails reduce unsupported claims but cannot prove usefulness or fair scores.
3. **Cross-device voice and performance:** microphone permissions, Piper voices, latency, memory, and model compatibility need tests on the user's Apple Silicon, Windows, and Linux devices. Fresh synthetic 4B/9B measurements on the reference Intel Mac are in [LOCAL_MODEL_QUALIFICATION.md](LOCAL_MODEL_QUALIFICATION.md); they do not qualify other devices or a real ten-answer package.
4. **Adaptive quality:** the first policy makes narrow, replayable choices and can fall back to fixed. It has not passed a real-user pilot, broad question-quality review, or an outcome study. A larger bank and reviewed variants are needed for a convincing adaptive interview.
5. **Hostile same-account process:** filesystem checks and owner-only permissions do not defend against malware already running with the user's account permissions. Keep the OS account and private backup safe. Historical snapshots created before privacy filtering may still contain sensitive facts; use the deliberate `delete-run` command to remove affected runs after making any backup you need.

These are validation limits or an operating-system trust boundary. They cannot be closed credibly by passing synthetic unit tests alone.

The fresh model check exposed another evaluation-quality limit: roughly equivalent English, Japanese, and Traditional Chinese answers received materially different scores from both models. The report labels scores as session evidence, but cross-language calibration has not been demonstrated. A native-speaker review and a larger, controlled multilingual evaluation set are required before treating those numbers as comparable. The 4B English strength note was too terse in one case. These are model-behavior findings, not failures of the schema or file-security controls.

## Reproducing the checks

From `InterviewSimulator`, after `uv sync --locked --group dev`:

```sh
uv run python -m pytest -q
uv run ruff check src agents tests
uv run ruff format --check src agents tests
uv run mypy src/interview_simulator agents/interview_practice
node --check src/interview_simulator/static/app.js
node tests/browser_state.cjs
```

From `InterviewWiki`, run `../.venv/bin/python -m pytest -q` on macOS/Linux. Use the equivalent parent environment executable on Windows. A fresh advisory scan needs network access; scan the active environment with `pip-audit`. Never interpret an unavailable advisory service as a clean result.
