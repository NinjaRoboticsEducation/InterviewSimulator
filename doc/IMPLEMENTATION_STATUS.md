# Interview Simulator implementation status

30 September 2026. This records what has been built from the [approved plan](INTERVIEW_SIMULATOR_RESEARCH_AND_IMPLEMENTATION_PLAN.md). It is a development status report, not a release certificate.

## Working baseline

- The local browser app lists manually prepared InterviewWiki opportunities, checks strict package and current PersonalWiki readiness without rewriting either wiki, and starts a separate run per opportunity and language. Its primary controls are translated for English, Japanese, and Traditional Chinese.
- A pinned Google ADK Python 2.10.0 `Workflow` owns ten user-input pauses and durable SQLite sessions. Each run has ten scored questions, two each about personal experience, professionalism, portfolio, role, and company, plus a greeting and closing. The fixed route prioritizes facts matched to job requirements, quotes a confirmed PersonalWiki fact where relevant, and uses validated company research excerpts when present.
- The question bank deduplicates question versions and concepts while retaining each presentation event. Answer submissions are idempotent. A restart test covers a saved answer that ADK had not yet acknowledged.
- The app supports typed responses and turn-by-turn voice. `whisper-cli` transcription preserves the raw recognition and separately saves the candidate-confirmed text. macOS `say` and a configurable Piper backend produce local WAV speech. Traditional Chinese recognition and report feedback are normalized locally.
- The report scores each answer against five explicit dimensions, requires an exact quote from the confirmed answer, and leaves failed assessments visibly unavailable. A separate coaching pass suggests an answer structure and an example assembled from confirmed PersonalWiki facts with visible placeholders for unsupported details. Scores cannot be revised by coaching. Long report generation runs in a background task with progress polling and retry from saved results.
- The local language model is reached through ADK's LiteLLM adapter at a loopback-only llama.cpp endpoint. JSON output is constrained by a server-side schema and checked again in Python. The local server launch with an API key and restricted origin was exercised successfully.

## Measured on the target Mac

The test machine identifies as Mac mini `Macmini8,1`, 3 GHz six-core Intel Core i5, 32 GB RAM, macOS 15.7.9, x86_64. The model server was llama.cpp 0.3.0 build 10621, CPU-only with six threads and a 4096-token context. These timings include one local ADK request and Python setup on synthetic data; they are not throughput guarantees or a full interview benchmark.

| GGUF model | SHA-256 check | English assessment | English coaching | Result |
|---|---|---:|---:|---|
| Qwen3.5-9B Q4_K_M | Matched publisher's hash | 61.64 s | 55.73 s | Valid score and grounded coaching; high delay |
| Qwen3.5-4B Q4_K_M | Matched publisher's hash | 47.22 s | 28.98 s | Valid score and grounded coaching; faster fallback |

The 4B fallback also produced a validated Japanese assessment in 47.91 seconds and a Traditional Chinese assessment in 36.61 seconds. An earlier Japanese trial returned English feedback despite a Japanese locale; explicit Japanese instructions and a language validator corrected that case. More diverse prompts and native-speaker review are still required. A small ADK-to-9B JSON smoke response took 15.81 seconds including setup. The [9B GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/blob/main/Qwen3.5-9B-Q4_K_M.gguf) and [4B GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/blob/main/Qwen3.5-4B-Q4_K_M.gguf) pages publish the hashes used for verification.

The user preference remains 9B first for quality. On this CPU, a full report at the measured per-answer rate could take many minutes. The app therefore exposes background progress; use 4B if 9B is not responsive enough for the user. The two models have not been tested against a real prepared job package, so neither is fully qualified for score fairness or all three interview languages.

## Verification completed

Automated tests cover ADK graph and local adapter contracts, fixed-question coverage and evidence references, answer replay, score immutability, report rendering, UI report progress, read-only wiki preflight, and InterviewWiki's simulation ownership rule. The simulator and nested InterviewWiki suites, Ruff lint and formatting, mypy, and inline browser JavaScript syntax have passed. Synthetic local speech round trips were exercised for English, Japanese, and Mandarin on this Mac; the Chinese transcript needed local Traditional conversion.

## Open release gates

1. Run a complete interview on an actual strictly validated opportunity and confirm the report with the user. No real PersonalWiki or job package was created or changed during development.
2. Review ten-question coverage, answer scoring, coaching examples, and voice quality with native speakers in English, Japanese, and Traditional Chinese. Expand the test cases for weak, unsupported, and contradictory answers.
3. Qualify Piper voices and microphone capture on an Apple Silicon Mac, Windows PC, and Linux reference device. The Piper code is present, but no full three-language voice set was installed and tested here.
4. Add a verified portable export/restore and deletion workflow, including SQLite-consistent backups and private-data handling. Current setup requires copying project data only while the app is stopped.
5. Implement and shadow-test bounded answer-aware selection from the question bank before exposing adaptive mode. Fixed practice and bank capture are the current behavior.
6. Add a broader latency and memory matrix for 9B and 4B, including full ten-answer reports and multiple opportunity types. The measured sample is too small to certify smooth operation.

Until those gates pass, use this as a carefully tested fixed-practice development build. The [README](../README.md) gives setup steps and explains the job picker.

## Audit follow-up

The [30 September security and correctness audit](SECURITY_AND_CORRECTNESS_AUDIT.md) records request protection, concurrency/recovery, privacy filtering, audio, report, and dependency fixes. The updated checks pass 37 simulator tests and 25 InterviewWiki tests, plus lint, formatting, typing and JavaScript checks. It also identifies incomplete model provenance and semantic coaching validation as additional release blockers. Read that audit together with the open gates above.

## Follow-up implementation

The simulator now has an ADK Web chat agent, a bounded adaptive bank selector, per-answer local model provenance, controlled coaching guidance, portable backup/restore/delete commands, and report verification. The [audit follow-up](SECURITY_AND_CORRECTNESS_AUDIT.md#follow-up-implementation-status-30-september-2026) records what remains to be validated with real candidate data, native speakers, and other devices. The earlier “Open release gates” section above is historical planning context and should not be read as current feature inventory.

The [fresh local model qualification](LOCAL_MODEL_QUALIFICATION.md) measured both Qwen3.5 Q4_K_M sizes again on the reference Mac after other applications were paused. All three synthetic language cases completed for each model. The 9B model was slower but gave more specific English feedback; both models showed substantial score variation across roughly equivalent translated answers. The README uses these newer timings. The final automated pass completed **45 simulator tests, 25 InterviewWiki tests, Ruff lint and format, mypy (21 source files), and the browser-state harness**. Real-package, native-speaker, cross-device, and broader fairness checks remain open.
