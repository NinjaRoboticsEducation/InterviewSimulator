# InterviewSimulator refinement research and implementation plan

Research date: **1 October 2026**  
Status: **Approved by the user; implementation completed with qualification limits recorded in [the implementation status](REFINEMENT_IMPLEMENTATION_STATUS.md).**

The proposal below is retained as the approved design record. Commands and acceptance targets should be read alongside the current README and validation record; it does not claim every target platform has been physically qualified.

This plan extends the existing research plan and implementation. It addresses installation, local speech, provider selection, interview navigation, and the final report. It is based on the current source code, the existing audit and model qualification documents, and the official sources linked throughout this document. Provider capabilities and prices are a dated research snapshot, not permanent configuration values.

## 1. Recommended direction and confirmed decisions

The refinements are feasible within the current Python application. Keep Google ADK—the Agent Development Kit—as the workflow engine, FastAPI as the local web server, and SQLite as the local database. Add provider adapters, explicit interview states, and a redesigned browser interface. A replacement agent framework, a hosted database, and a large frontend framework are unnecessary for this scope.

The most significant work is below the visual interface: the current application assumes one local model and append-only answers. Provider selection and answer editing must change those assumptions safely before the new controls become available.

### Decisions confirmed by the user

| Area | Agreed behavior |
|---|---|
| Cloud processing | **Text tasks only.** Microphone audio, transcription, and speech generation remain local. Confirmed transcript text may be sent to the selected text provider for evaluation. |
| API keys | Offer optional storage in the operating system's credential vault. Default to keeping a newly entered key in server memory unless “Remember on this device” is selected. |
| Answer editing | Allow changes **before scoring starts**. Preserve the existing later question sequence. After scoring starts, answers are locked; further practice uses a new run. |
| Visual theme | **Modern Minimalist:** neutral grayscale with a quiet accent. |
| Local models | Qwen3.5-9B Q4_K_M first; Qwen3.5-4B Q4_K_M as the explicitly selected speed alternative. |
| Interview | Ten scored questions, plus an unscored greeting and closing; turn-by-turn speech without spoken interruptions. |
| Languages | English, Japanese, Traditional Chinese; Mandarin speech for Traditional Chinese. Reports follow the interview language. |
| Wiki preparation | PersonalWiki building and InterviewWiki registration/package generation remain manual prerequisites. The simulator reads the approved results. |
| Reference device | 2018 Mac mini, 3 GHz six-core Intel Core i5, 32 GB RAM, macOS Sequoia 15.7.9. Newer Macs and supported Windows/Linux PCs are additional qualification targets. |

Optional credential storage is device-specific: copying the project must not copy API keys. The new device reconnects its providers during setup.

### Scope boundaries

This release includes local and three first-party cloud text providers: Google Gemini Developer API, OpenAI API, and Anthropic Claude API. It does not include Vertex/Agent Platform enterprise authentication, Azure, Bedrock, remote multi-user hosting, cloud speech, voice cloning, or continuous live audio. Those require separate decisions and testing. Existing text practice in ADK Web remains supported; the guided voice experience belongs to the built-in browser.

## 2. What the current implementation can support

The inspected baseline pins `google-adk[db]==2.10.0`, supports Python 3.11–3.13, and uses a locked dependency file. The source already contains useful foundations: durable ADK interview turns, saved answers, question-bank selection, separate evaluation/coaching calls, guarded local speech, private database files, report manifests, and recovery tests.

| Current location | Finding | Required refinement |
|---|---|---|
| `config.py` | The model URL is intentionally restricted to loopback, meaning this computer. | Keep this restriction for local models. Introduce separate cloud provider profiles; do not turn the local URL setting into an unrestricted outbound URL. |
| `adk_runtime.py` | `LocalAdk` creates an OpenAI-compatible local client, passes llama-specific settings, and uses a 320-token output budget for model tasks. | Create task-specific ADK model adapters. Translate schema, reasoning, and token settings per provider. A longer coaching task must have its own tested output allowance. |
| `provenance.py`, `engine.py` | Scores are tied to the local GGUF file fingerprint. Coaching currently expects the same model identity. | Record separate model identities for question generation, scoring, coaching, and summary. Keep the evaluator fixed within one scoring snapshot, while allowing a different coach. |
| `storage.py`, `InterviewFlow` | Answers and ADK events are append-oriented; progress is derived from submitted answers. | Add explicit navigation, answer versions, and an atomic transition to scoring. Reading an earlier question must not replay a submission. |
| `engine.py:state` | State reconciliation can acknowledge events or commit selection decisions. | Separate read-only review from forward progression. A history page must not choose a new question as a side effect. |
| `questions.py`, `selection.py` | Prepared questions and a constrained bank provide predictable delivery. Adaptive selection is currently a bounded heuristic. | Add optional ADK-generated variants with fact checks; preserve category coverage. Evaluate Japanese/Chinese matching rather than relying on whitespace-style word matching. |
| `evaluation.py` | Grounding checks intentionally constrain coaching examples. | Improve helpfulness through a richer, evidence-linked coaching schema. A stronger model alone will not remove template limitations safely. |
| `report.py`, `static/app.js` | Markdown is generated safely but displayed as text in the browser. | Add sanitized HTML and a structured score view without giving generated content permission to execute scripts. |
| `speech.py`, `/api/speech` | Local whole-turn speech and inexpensive readiness checks exist. Non-Mac speech assumes configured Piper models. | Retain these protections and add verified platform/language adapters, installation guidance, and actual sample playback/transcription checks. |

This is an architectural review, not a new claim that every source line has passed a fresh security audit. The prior [security audit](SECURITY_AND_CORRECTNESS_AUDIT.md), [implementation status](IMPLEMENTATION_STATUS.md), and [local model qualification](LOCAL_MODEL_QUALIFICATION.md) remain relevant. Existing uncommitted voice fixes must be preserved during implementation.

### Practical performance expectations

The reference Mac's recorded synthetic English assessment plus coaching took **142.45 seconds with 9B** and **92.72 seconds with 4B**. Each was a small sample, not a production latency guarantee. Prepared question delivery does not need to wait for scoring. Keep expensive evaluation after the final answer, display real progress, and save completed work incrementally. Cloud text may reduce the CPU burden, but its response time still depends on the network, provider load, reasoning settings, and output length. See the [measured conditions and language-quality limits](LOCAL_MODEL_QUALIFICATION.md).

The existing multilingual samples produced materially different scores for roughly equivalent answers. New cloud models must pass application-specific evaluation; their general reputation does not establish fair interview scoring.

For installation planning, use the following engineering targets rather than claiming universal hardware support:

| Profile | Proposed hardware target | Qualification status |
|---|---|---|
| Local 9B plus voice | The reference 32 GB Intel Mac; conservatively 32 GB RAM on other CPU-based PCs | Reference synthetic checks exist; other devices need their own measurements |
| Local 4B plus voice | 16 GB or more RAM, a recent multi-core processor, and adequate free disk | Proposed lower-memory target, not yet a measured guarantee |
| Cloud text plus local voice | 8–16 GB or more RAM; CPU capacity still matters for Whisper | Text inference is remote; benchmark transcription before promising responsiveness |
| Cloud text only | A supported Python-capable desktop with a current browser and reliable network | Lowest local resource demand; no Qwen or voice-model download |

Calculate free-disk requirements from selected model and native-tool manifests, including temporary download/build space. Do not advertise one storage number for every profile.

## 3. Current provider and model research

### 3.1 Text model candidates

These are candidates for qualification, not claims that paid inference has been tested in this project. The application should discover the user's models and display verified compatibility. It must not automatically switch a saved interview to a newer release.

| Provider | Candidate for initial qualification | Other useful comparisons | Application recommendation |
|---|---|---|---|
| Local | Qwen3.5-9B Q4_K_M | Qwen3.5-4B Q4_K_M | Preserve the user's quality-first default; use prepared questions and serialized local inference on the Intel Mac. |
| Google | `gemini-3.8-flash`, listed as stable | Available Pro or other stronger models after separate compatibility checks | Begin with Flash for question variants, evaluation, and coaching. Select on measured quality and latency, not the family name. [Google model catalog](https://ai.google.dev/gemini-api/docs/models), [Flash specification](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash). |
| OpenAI | `gpt-6.1-sol` | `gpt-6-astra` for quality comparison; `gpt-6-luna` for inexpensive focused tasks | Qualify Sol for scoring/coaching; test Luna before using it to grade candidates. [Current catalog](https://developers.openai.com/api/docs/models/all), [Sol specification](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [Luna specification](https://developers.openai.com/api/docs/models/gpt-6-luna). |
| Anthropic | `claude-sonnet-5-5` | Opus 5.5 for quality comparison; Haiku 4.5 for lighter tasks | Qualify Sonnet first for scoring and grounded coaching. The catalog also lists Fable 5.1, but its cost and operational constraints do not make it the initial default. [Claude model overview](https://platform.claude.com/docs/en/models/overview). |

There are concrete compatibility traps:

- GPT-6.1 Sol supports Chat Completions without tool calling; tool use requires Responses. Its reasoning settings do not include `none` or `minimal`. Do not assume the current local adapter's parameters will work unchanged. [Sol API behavior](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
- Gemini 3.8 Flash supports structured output, but `minimal` thinking is not a supported setting. It accepts audio input but does not generate audio; text-model selection is not TTS selection. [Flash capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash).
- Claude Sonnet 5.5 rejects forced tool use and non-default sampling values such as `temperature=0.2`. Use supported structured output rather than a universal forced-tool workaround. [Sonnet 5.5 behavior](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).

The initial app does not need model-selected tools for grading. Each model receives bounded evidence and returns a validated object. This keeps compatibility simpler and prevents a question or answer from instructing a model to read files, run commands, or contact another service.

### 3.2 Model discovery, authentication, and SDKs

An API is the provider's programmatic interface; an SDK is a Python library that helps call it.

| Provider | Server-side discovery and authentication | What the result establishes | Python/ADK approach |
|---|---|---|---|
| Local | Configured loopback `/v1/models`; retain `/props` and GGUF verification | Models actually served by that llama.cpp instance; not all downloaded models | Existing OpenAI-compatible transport through an ADK model connector |
| Google | `GET https://generativelanguage.googleapis.com/v1beta/models`; `x-goog-api-key` header | Model names, supported generation methods, token limits; paginated | Native ADK Gemini connector with an explicitly scoped `google-genai` client |
| OpenAI | `GET https://api.openai.com/v1/models`; `Authorization: Bearer …` | IDs and metadata, not a complete task-capability matrix | ADK connector supported by the pinned version; use LiteLLM where verified or an ADK `BaseLlm` adapter for the required API |
| Anthropic | `GET https://api.anthropic.com/v1/models`; `x-api-key` and `anthropic-version` headers | IDs, pagination, token limits and capability metadata, which may be absent/null | Verified ADK/LiteLLM connector with a scoped client; declare `anthropic` directly if its SDK is used |

Sources: [Google models API](https://ai.google.dev/api/models), [Google key authentication](https://ai.google.dev/gemini-api/docs/api-key), [OpenAI model listing](https://developers.openai.com/api/reference/resources/models/methods/list), [Anthropic model listing](https://platform.claude.com/docs/en/api/http/models/list), [ADK model integration](https://adk.dev/agents/models/).

Google's current key guidance distinguishes newer authorization keys from restricted standard keys; unrestricted standard keys are rejected. The setup guide should link to the current provider console and explain authentication failures without printing the key. Browser-origin-restricted keys may also be unsuitable for backend requests. [Google key guidance](https://ai.google.dev/gemini-api/docs/api-key).

Model discovery should work as follows:

1. Accept a provider and key through the protected local server. Contact only that provider's approved HTTPS host.
2. Retrieve every page with bounded timeouts and response-size limits. Do not send candidate information during discovery.
3. Normalize the result into a catalog with model ID, display name, input/output types, schema support, supported controls, lifecycle status, and evidence date. Represent missing facts as **unknown**, not false or assumed supported.
4. Merge provider metadata with a small, versioned compatibility registry derived from official documentation and contract tests. This registry supplements live discovery; it does not replace it with a fixed menu.
5. Show compatible text models first. Explain why other models are unavailable for a task. Newly discovered IDs can appear as “Not yet verified.”
6. Offer a small synthetic compatibility check before first use, with notice that it may incur API charges. Listing success alone does not prove inference quota, billing, schema compatibility, or language quality.
7. Cache by credential profile and provider for a short period, initially 15 minutes. Provide Refresh. Stale cached data must be labeled and revalidated before a new run.

Keep the requested model ID and the returned model identifier. Prefer stable versions where available. If a model disappears, pause the affected task and request a new selection; never silently send the candidate's data to another provider.

### 3.3 Separate models for separate tasks

Use a simple default—one model for all text tasks—and an expandable “Advanced model settings” section. Advanced settings may choose different configured providers, with clear disclosure of which receives each task.

| Task | What it needs | Proposed execution |
|---|---|---|
| Question preparation | Relevant, varied questions grounded in job and candidate evidence | Optional ADK question agent, before the interview; validate ten questions and category coverage. Prepared package questions remain an explicit fallback. |
| Next-question selection | Natural progression within a valid question deck | Deterministic constraints first; bounded bank selection. Do not require a large reasoning call on every button click. |
| Answer evaluation | Consistent rubric, exact answer evidence, structured scores | Dedicated ADK evaluator; one frozen evaluator configuration for all ten questions in a scoring snapshot |
| Coaching examples | Useful answer structure without invented career facts | Separate ADK coach using confirmed fact IDs, the answer, and the saved assessment |
| Overall narrative | Summarize already validated findings into priorities | Optional ADK summary agent; it cannot modify numbers or introduce new candidate claims |
| Report formatting | Correct tables, layout, totals and charts | Ordinary Python and HTML rendering; no model needed |
| STT: speech to text | Transcribe local audio accurately | Local whisper.cpp multilingual model only |
| TTS: text to speech | Read the question in the selected language | Local OS voice or verified local TTS model only |

Initial model-task budgets must be measured rather than copied from provider maximums. A proposed starting experiment is 1,024–2,048 output tokens for one assessment and 2,048–4,096 for coaching, adjusted separately for local CPU use and providers that count reasoning within the output allowance. Question preparation should be bounded by a ten-question schema and context budget. The existing local 320-token path should remain a benchmark comparison, not be replaced blindly with a much slower setting.

### 3.4 Speech research and the local-only decision

Cloud speech is technically available, but **will not be enabled in this release**. OpenAI currently lists `gpt-transcribe` for file/turn transcription and `gpt-4o-mini-tts` for speech generation. Google lists Gemini 3.5 Transcribe and Gemini 3.8 Flash TTS families. Standard Claude models in the reviewed catalog produce text, so an Anthropic text selection would still need a separate voice engine. Sources: [OpenAI transcription](https://developers.openai.com/api/docs/models/gpt-transcribe), [OpenAI TTS](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts), [Google catalog](https://ai.google.dev/gemini-api/docs/models), [Claude catalog](https://platform.claude.com/docs/en/models/overview).

Keep voice settings independent from the text provider. Do not use browser speech recognition as an automatic substitute: browser behavior may involve a remote service. Record through the browser microphone, upload only to the loopback server, transcribe locally, and let the user correct the text before submission. Keep raw audio temporary unless a future explicit recording-retention feature is approved.

For recognition, retain **multilingual whisper small** as the baseline. A multilingual base model can be offered as a speed/accuracy tradeoff after testing. English-only `.en` models cannot satisfy the three-language requirement. The executable and its model are separate installations. [whisper.cpp installation and models](https://github.com/ggml-org/whisper.cpp).

For playback:

| Platform | Recommended route | Qualification needed |
|---|---|---|
| macOS | Installed `say` voices: English, Japanese, Mandarin; select by language and verify the voice exists | Download missing voices through system settings; test actual playback. Do not assume every Mac has Samantha, Kyoko, and Meijia. [Apple voice setup](https://support.apple.com/en-lb/guide/mac-help/mchlp2290/mac). |
| Windows | Add a Windows local speech adapter using installed system voices; Piper remains optional | Enumerate voices through the chosen Windows API and test all three languages. Do not assume voices visible to one Windows speech API are visible to another. [Microsoft voice enumeration](https://learn.microsoft.com/en-us/uwp/api/windows.media.speechsynthesis.speechsynthesizer.allvoices?view=winrt-28000). |
| Linux | Piper for verified English/Mandarin models; evaluate Open JTalk for Japanese | Test engine, dictionary, voice, pronunciation and packaging together. Open JTalk is a local Japanese TTS candidate, not yet a project-qualified substitute. [Open JTalk](https://open-jtalk.sp.nitech.ac.jp/). |

Use the maintained [OHF Piper project](https://github.com/OHF-Voice/piper1-gpl), rather than treating the archived repository as the installation authority. The engine uses GPL licensing and voice files have their own licenses. The reviewed [voice instructions](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md) do not establish a ready, tested Japanese voice path for this application. Do not advertise universal Piper coverage. A Mandarin model trained for Simplified Chinese also needs pronunciation testing with Traditional Chinese input; any conversion should affect only the speech copy, never the saved answer or report.

Full Windows/Linux voice support is a release gate. Missing voices should produce a precise setup instruction and allow typed practice; typed fallback alone does not qualify a platform as fully voice-supported.

### 3.5 Cost, latency, and privacy

The following standard text rates were listed on the research date. Amounts are US dollars per million input/output tokens. Tokens are the pieces of text a provider meters; thinking, retries, caching, and service tiers can change billing.

| Example model | Input | Output | Illustration: 50,000 input + 10,000 billable output tokens |
|---|---:|---:|---:|
| Gemini 3.8 Flash | $0.75 | $3.75 | $0.075 |
| GPT-6.1 Sol | $2.00 | $10.00 | $0.20 |
| GPT-6 Luna | $0.10 | $0.50 | $0.01 |
| Claude Sonnet 5.5 | $2.00 | $10.00 | $0.20 |

These are arithmetic examples, **not measured interview costs**. Google's displayed Flash rates run through 31 December 2026; its page lists higher rates from 1 January 2027. Sources: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), [Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna), [Sonnet pricing](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).

Before a run, show a dated estimate or “Price unavailable,” with an optional spending limit. Record reported token usage and estimated cost per task. Never invent a price for an unknown model. Cap requests and output budgets locally; the provider's billing dashboard remains authoritative. A timeout can occur after the provider has done billable work, so retries must not be described as free.

Cloud mode sends selected job facts, approved candidate facts, questions, and confirmed answer text to the chosen provider. Show this plainly before starting; do not send an entire wiki, raw resume files, contact details, or unnecessary source documents. Keep audio local even when the transcript goes to cloud scoring.

Provider privacy is not uniform. Google's pricing page distinguishes free-tier content use from paid-tier treatment. OpenAI documents endpoint-specific retention, including default abuse-monitoring retention of up to 30 days and additional application-state behavior; `store=false` is not a universal zero-retention guarantee. Anthropic also documents feature- and model-specific rules, including special requirements for Covered Models. Link these policies from setup and avoid promising that “local app” means “cloud data is never retained.” Sources: [Google pricing/data-use distinction](https://ai.google.dev/gemini-api/docs/pricing), [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Anthropic retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention).

## 4. Architecture and configuration

### 4.1 Keep ADK in control

ADK supports native models and model connectors, including LiteLLM. This permits multiple providers without replacing the workflow. The installed version's connector behavior must be tested against selected models; current online documentation does not prove that every new model works through the locked dependency set. [ADK model architecture](https://adk.dev/agents/models/).

```text
Prepared PersonalWiki + InterviewWiki (read only)
                    |
          Evidence snapshot + job selection
                    |
Built-in browser ---+--- ADK Web text commands
                    |
        Shared interview service and storage
                    |
        ADK Workflow / Runner / sessions
          |            |             |
      Questions     Evaluator       Coach ---- Summary
          +------------+-------------+             |
                    |                              |
         Per-task model adapter              Validated results
          |       |        |       |                |
        Local   Google   OpenAI  Anthropic      Markdown + HTML

Browser microphone -> local FFmpeg -> local whisper -> reviewed text
Question text -> local speech adapter -> browser playback
```

Provider SDKs handle discovery and model transport. Model-task orchestration, invocation tracking, and interview flow remain in ADK. Do not add a second, parallel agent framework. Preserve the fixed practice route while the new question agent is qualified.

### 4.2 Configuration model

Introduce a typed **model binding**, meaning a saved choice of provider, model, and supported options for one task. Validate all options against capabilities before creating an agent. Do not forward arbitrary browser-supplied provider parameters.

Illustrative non-secret configuration—not a supported file format yet:

```json
{
  "schema_version": 1,
  "text_tasks": {
    "questions": {"provider": "local", "model": "interview-local"},
    "evaluation": {
      "provider": "openai",
      "model": "gpt-6.1-sol",
      "credential_ref": "profile-7",
      "reasoning": "medium"
    },
    "coaching": {
      "provider": "anthropic",
      "model": "claude-sonnet-5-5",
      "credential_ref": "profile-9"
    },
    "summary": {"inherit": "coaching"}
  },
  "speech": {
    "processing": "local_only",
    "stt": "whisper_cpp",
    "tts": "platform_default"
  }
}
```

Resolve inheritance once at run creation. Save a non-secret immutable run model plan, including prompt/rubric/schema versions, adapter version, requested model, supported controls, and local file hashes where applicable. After a call, append the returned model ID, provider request ID when available, usage, and input/answer-version hashes. Cloud provenance records service identity; it cannot attest to provider weights as a local GGUF hash can.

Freeze scoring against an `answer_snapshot_id`. The evaluator cannot change midway through that snapshot. A different coach is allowed and labeled. Reconnecting a key for the same configured model should allow unfinished work to resume; changing the evaluator requires a new scoring run, not mixing old and new scores.

### 4.3 API-key handling

The requested browser key-entry field necessarily holds the typed key briefly. The achievable security promise is: **the app never embeds saved keys in frontend assets, echoes them through its API, or persists them in browser storage**. A password field is not protection against a compromised browser extension or operating-system account.

Proposed handling:

- Send the key once to a protected loopback endpoint; clear the input after acceptance. No key in URLs, chat messages, localStorage, sessionStorage, reports, screenshots used for tests, or error text.
- Use server-only credential objects with redacted representations. Never place credentials in ADK state/events, saved model plans, tracing payloads, or agent serialization. `SecretStr` helps but does not replace explicit output schemas and leak tests.
- “Remember on this device” uses a validated OS vault backend: macOS Keychain, Windows credential storage, or Linux Secret Service/KWallet. Offer session-only operation if the vault is unavailable or locked. Never fall back to a plaintext keyring backend.
- Namespace vault entries by application installation/profile ID so two project copies do not accidentally share, overwrite, or delete one another's secrets. A copied installation detects a new device/profile and asks to reconnect.
- Provide Disconnect, Forget saved key, and Replace key. Keys are excluded from backups, exports, diagnostics, and Git. Do not write cloud keys to the current `.env` file.
- Keep HTTP clients scoped to a provider/profile. Do not mutate process-global API-key variables when a user changes providers. Redact authorization headers and provider exceptions; disable prompt/key-bearing telemetry and debug logs.
- Preserve host/origin checks, anti-forgery tokens, loopback binding, restrictive browser security policy, and no permissive cross-origin access. Cloud clients use HTTPS, approved hosts, no arbitrary redirects, and explicit proxy policy. Local inference retains its separate loopback restriction.

For session-only keys in ADK Web, prompt securely in the terminal during server startup and retain the key in that server process. A separate short-lived CLI process cannot hand over a memory-only key simply by exiting. Saved profiles may instead resolve their key from the OS vault. Moving between the two interfaces after stopping a server therefore requires re-entry for session-only credentials.

The `keyring` library provides OS backend integration, but its documentation notes that macOS secrets can be accessible to other scripts using the same permitted Python executable. The vault protects stored credentials; it is not isolation from all code running as the same user. Document the platform behavior and test lock/unlock and denied access. [Python keyring documentation](https://keyring.readthedocs.io/en/latest/).

### 4.4 Reliability and interruption handling

Use explicit connect, read, and whole-task deadlines. Retry transient 429/5xx failures with a small capped backoff and respect `Retry-After`. Do not repeatedly retry invalid credentials, unsupported parameters, malformed requests, or failed local schema checks. A single structured-output repair can be allowed with a separate recorded attempt and budget.

Save each valid assessment before coaching. If a cloud request times out ambiguously, mark the attempt unresolved and disclose possible duplicate cost before a user-triggered retry. Local request IDs prevent duplicate database writes but do not guarantee provider-side exactly-once billing. Cancellation must stop pending local work where possible and ignore late results for canceled runs; it cannot guarantee that a remote provider stops billing.

Keep local CPU inference and local speech under a resource policy suitable for the reference Mac. Use a separate, small concurrency limit for cloud I/O; do not launch ten grading calls at once by default. Neither model work nor vault calls may block the web event loop.

## 5. Installation and the future user manual

### 5.1 Dependency groups

| Group | Needed for | Contents |
|---|---|---|
| Core Python | Every installation | Supported Python, uv environment, ADK, FastAPI/Uvicorn, SQLite integration, validation, wiki reader, locked dependencies |
| Cloud text | Selected cloud provider | Internet access, provider API account/key, compatible adapter/SDK; no llama-server or Qwen download required |
| Local text | Qwen inference | Compatible llama.cpp build, verified Qwen GGUF, local model settings |
| Voice input | Microphone answers | Browser microphone permission, FFmpeg, whisper-cli, a real multilingual Whisper model |
| Voice output | Read-aloud questions | Installed OS voice or local TTS engine plus language-specific model/dictionary assets; FFmpeg where format conversion is required |
| Credential vault | Remember keys | Python keyring plus an approved platform backend |
| Development | Contributors and test runs | Ruff, mypy, pytest, browser automation and accessibility test tooling |

`pyproject.toml` can declare Python dependencies and optional extras, but cannot by itself install every native executable, OS voice, model file, or microphone permission. Use a guided bootstrap script plus a checked download manifest. `uv.lock` should remain the reproducible Python source of truth. [uv project management](https://docs.astral.sh/uv/guides/projects/).

### 5.2 One-command setup: feasible with limits

Provide reviewed scripts in the cloned repository. These are **proposed commands, not commands available today**:

```sh
# macOS/Linux, after cloning and opening the project directory
./scripts/setup.sh --profile local-voice
```

```powershell
# Windows, after cloning and opening the project directory
.\scripts\setup.ps1 -Profile local-voice
```

Profiles: `cloud-text`, `cloud-local-voice`, `local-text`, and `local-voice`. A cloud-only installation must not fail because llama.cpp or a GGUF is absent. A text-only installation must not require a microphone.

The bootstrap should detect OS/CPU architecture and supported Python; show planned downloads, disk requirements and licenses; install/sync the Python environments; locate or help install native tools; download selected models with checksums; write only non-secret project-relative settings; then run diagnostics. Use one common Python setup module behind the shell/PowerShell entrypoints. Support `--dry-run`, resumable downloads, reruns without duplicate work, and an installation receipt.

Native package installation may require an administrator prompt, and OS voice installation may require a settings interaction. Do not disable operating-system security policies, run `sudo pip`, or silently upgrade unrelated system packages to make “one command” appear complete. If a prebuilt binary is unavailable, give a tested source-build path or stop that optional component with a precise instruction.

Platform details matter:

- **Intel Mac:** preserve the known working CPU configuration. Detect tools rather than hardcoding `/opt/homebrew`; Intel Homebrew commonly uses a different prefix. The current Homebrew Whisper formula is named `whisper.cpp` and says models are separate downloads. Its displayed bottle support does not establish an Intel macOS binary path, so test source builds or a pinned compatible release on the actual reference machine. [Homebrew formula](https://formulae.brew.sh/formula/whisper.cpp).
- **Apple Silicon:** select native ARM tools, avoid accidentally mixing translated Intel executables, and qualify Metal acceleration with the chosen llama.cpp build. Retain CPU fallback. [llama.cpp build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md).
- **Windows:** use native paths, correctly handle spaces/non-ASCII filenames, detect required runtime libraries, and use trusted upstream builds or a documented CMake/toolchain route. Do not make WSL a hidden prerequisite.
- **Linux:** target one documented baseline initially, such as Ubuntu LTS, with package checks and source-build fallbacks. Other distributions are best-effort until tested. Use the platform's FFmpeg package or a build referenced by the official project. [FFmpeg downloads](https://ffmpeg.org/download.html).

Pin native releases and model manifests after qualification. Do not download from mutable `latest` URLs without recording the resolved release and verifying its integrity. Each model entry should include source URL, revision, size, SHA-256, license, and intended language/task. Preserve existing large files if their hashes match. Never overwrite `.env`, wiki data, reports, or installed user models automatically.

### 5.3 README structure and acceptance

The rewritten README should be a usable manual, with separate detailed installation pages where necessary:

1. **What InterviewSimulator does:** an example practice session; local/cloud text choice; local speech; honest meaning of the score.
2. **Choose an installation:** hardware table, four profiles, dependency matrix, OS-specific steps, exact model downloads and checks, expected disk space from the manifest.
3. **Prepare your information:** copy the resume into PersonalWiki, register sources, run ingestion/review and strict lint; register the job in InterviewWiki, prepare/research/validate/finalize the package. Explain that source registration and task preparation alone do not generate the complete wiki/package. Reuse the real commands and nested project guidance already present in the repository.
4. **Check speech:** verify executables and model files, enumerate/download voices, select the language, run sample playback and recognition, explain microphone permissions and typed fallback.
5. **Start practice:** optionally start llama-server, then `uv run interview-simulator serve` and open `http://127.0.0.1:8765`. Explain provider/key/model selection and each guided screen.
6. **Use ADK Web:** `uv run interview-simulator serve-adk`; choose the agent and a ready job. Keep shared engine behavior and document text-only controls. Configure secrets outside chat through an interactive server-side CLI or the OS vault. Stop one interface before opening the other on the same port.
7. **Review results:** review all answers before scoring, read the HTML report, download Markdown, locate each run under the job's `Simulations` folder, retry incomplete coaching, and practice again.
8. **Maintain and move the project:** recreate environments on another device, revalidate native tools, copy private data intentionally, reconnect vault keys, run migration checks and verify report manifests.
9. **Troubleshoot:** symptom → likely cause → exact check → next action. Include missing model, copied paths, blocked mic, silent audio, wrong language, no ready jobs, invalid key, quota, offline provider, unavailable vault, slow report and interrupted setup.

Every command must be exercised on a clean test installation before being described as supported. Do not put development dependencies in the ordinary user install unless the user chooses them.

## 6. Modern Minimalist interface and guided flow

The design direction uses Frontend Design and Theme Factory guidance with the user's confirmed Modern Minimalist theme. The application does not depend on workstation-specific skill files.

### Visual system

Use white content surfaces, charcoal `#36454f` for primary text and actions, slate `#708090` for restrained accents, and light gray `#d3d3d3` for borders. Do not use slate for small text on white without checking contrast. Reserve accessible success/warning/error colors for status, always with text and icons.

Use DejaVu Sans where bundled and licensed, with tested local Japanese/Traditional Chinese fallbacks. Do not load font or chart assets from a third-party CDN. Use an 8-pixel spacing rhythm, readable 16–18-pixel body text, comfortable line spacing, modest corner rounding, and clear keyboard focus. Test text contrast to WCAG AA targets, touch targets, zoom, reduced motion, and screen-reader labels.

The defining layout is a quiet interview desk: a narrow setup/progress rail, one prominent question, and a generous answer area. Avoid a dashboard full of equal-weight cards, decorative gradients, oversized score badges, or animations that distract from speaking.

```text
InterviewSimulator                 Job: Product Designer       Settings
---------------------------------------------------------------------
1 Connection   2 Models   3 Job   4 Readiness   5 Interview   6 Report
---------------------------------------------------------------------
Experience       QUESTION 4 OF 10                    Saved 14:32
Professional     Tell me about a project where you changed direction.
Portfolio  <     [Play question]  [Stop audio]
Role
Company          Your answer
                 +------------------------------------------------+
                 | Type here, or record and review the transcript. |
                 +------------------------------------------------+
                 [Record answer]                Microphone ready

                 [Previous]              [Save answer and continue]
                 Review answers                              End practice
---------------------------------------------------------------------
Text: Local Qwen 9B                       Speech stays on this device
```

On small screens, replace the side rail with a compact progress strip. Keep the primary action visible without covering the answer. Every asynchronous operation needs a meaningful state: connecting, checking models, preparing questions, recording, transcribing, saving, evaluating, or retrying.

### End-to-end flow

1. **Connection:** Local selected by default. Its readiness check explains how to start llama-server. Choosing a cloud provider removes the local-server requirement and offers key entry plus optional vault storage.
2. **Models:** one recommended compatible text model, with advanced per-task settings. Read-aloud and transcription settings clearly say Local.
3. **Job:** show ready opportunities with company, role, language/package status and last updated date. Incomplete packages remain visible with instructions for the manual prerequisite workflow.
4. **Readiness:** language, fixed/adaptive mode, selected candidate profile, ten-question scope, voice tests, and disclosure of text sent to each provider. Keep secrets and unnecessary candidate details off the summary.
5. **Interview:** play the greeting on user action, ask the introduction question, progress through the topic groups, then close. Answer by typing or recording → review transcript → confirm. Avoid automatic microphone activation.
6. **Review:** list all ten questions, confirmed answers and explicit skips. Allow corrections. Explain that Generate report locks answers for scoring.
7. **Report:** display saved progress, then formatted results. Offer Markdown download, print-friendly view, retry unfinished work, and Practice again for the same job.

Use plain actions such as “Check connection,” “Save answer,” and “Review before scoring.” Error messages should describe the failing step and a recovery action without discarding typed text. Keep interface strings in locale dictionaries so Japanese and Traditional Chinese are not embedded inconsistently in JavaScript.

## 7. Interview state, edits, and question quality

### State and navigation rules

```text
Setup -> Preparing -> Interviewing -> Reviewing -> Scoring -> Completed
                         |              |           |
                         +--- Paused <--+           +-> Incomplete report
                         |                              |
                         +-> Cancelled                  +-> Retry unfinished work

Restart / Practice again -> a NEW run; previous run remains available
```

Separate the **review cursor**—the question currently being viewed—from **progress**, the number of confirmed answers/skips. Going back is a read operation. Saving an edit creates a new answer version within the same unscored run. Keep a small audit trail and mark older versions superseded; reports use the final confirmed version only.

Back/edit must not re-run question selection, regenerate questions, or change already planned later question IDs/order. Previously committed adaptive decisions remain recorded, including the answer version originally used for selection. Any unselected future slot is selected only through normal forward progression, never as a side effect of viewing or editing history. The app should explain that editing does not redesign the existing interview sequence.

ADK's earlier answer events remain historical. The engine must use the canonical confirmed answer version for evaluation, rather than reconstructing final answers by blindly replaying the original event stream. Add an explicit correction record/overlay and contract tests for ADK resume. Do not patch or delete old ADK events to simulate time travel.

Use a database transaction to prevent an edit/scoring race. Illustrative service logic:

```text
BEGIN IMMEDIATE
  load run and expected version
  reject if version is stale or run is scoring/completed
  if editing: append answer version; update canonical pointer
  if starting scoring:
      verify 10 answered-or-skipped slots
      persist immutable answers + question IDs + model plan
      set scoring snapshot ID and lock answers
  increment run version
COMMIT
```

Both the built-in browser and ADK text commands call this same service. An outdated tab receives a conflict response and reload instruction, not silent last-writer-wins behavior. Duplicate Submit/Generate report requests use request IDs and cannot create duplicate answers or jobs.

“End practice” offers save-and-exit or cancel-run behavior with clear wording. Cancellation preserves history but stops further work; restart creates a new run. If scoring has started, stopping the report leaves an incomplete, resumable scoring snapshot; it does not unlock graded answers. Support crash recovery without requiring the browser tab to remain open.

### Question generation and adaptive practice

Preserve two questions in each of five topic groups: personal experience, professionalism, portfolio, role, and company. Greeting/closing do not count toward ten. Start with introduction and accessible experience questions before deeper evidence and role-specific questions.

The optional question agent should output question text, category, difficulty, competency, fact/source references and a grounded follow-up purpose. Validate counts, unique IDs, language/script and references. Treat wiki contents and candidate answers as evidence, never as instructions that override the workflow. Do not let the model introduce unsupported personal claims inside a question.

Prepare enough validated questions before the interview to avoid long waits between turns. Store unique questions with provenance and locale; use normalized exact matching first and cautious semantic duplicate review later. Do not merge questions merely because their embeddings are close. Exclude greetings/closings from the scored question bank.

For adaptation, constrain selection by remaining topic coverage, interview stage, difficulty progression and available evidence. Maintain the fixed route when the bank is small or selection confidence is low. Replaying a question, editing an answer, or refreshing a page must not count as another interview exposure. This is controlled question-bank selection, not model training; success must be measured on realism and usefulness, not claimed from bank size alone.

### Local voice interaction

Retain explicit Record/Stop/Review/Confirm steps, a recording timer, duration/upload limits, and a text alternative. Stop playback before recording. Canceling or leaving a screen must close microphone tracks and stop playback; delayed permission responses must not reopen a canceled recording. Support actual Safari MP4 and Chromium/Firefox WebM formats through local conversion, rather than assuming one MIME type.

Show readiness by selected language. A working English voice should not imply that Japanese works. Test silence, denied permissions, disconnected microphones, corrupted files, long recordings, no speech recognized, and native process timeouts. Save confirmed text, not an unreviewed transcription, as the answer used for scoring.

## 8. Report design and grounded career coaching

### Safe Markdown-to-HTML rendering

Keep `report.md` as a portable artifact and create a structured report view model from validated results. Render Markdown with raw HTML disabled, then sanitize with a strict allowlist before returning HTML. Candidate text and model output are untrusted. Block scripts, event handlers, embedded forms, arbitrary styles, iframes, external images and unsafe URL schemes. External links should use safe schemes and appropriate browser protections.

Candidate dependencies to qualify are `markdown-it-py` for Markdown and `nh3` for HTML sanitization, with autoescaped templates if needed. The parser's default permits raw HTML, so explicitly use a safe preset/options; the sanitizer must also have an application-specific tag/attribute/URL policy. Test the locked versions and wheel availability across supported platforms. Do not solve formatting by assigning raw Markdown or unsanitized model HTML to `innerHTML`. Sources: [Markdown parser security](https://markdown-it-py.readthedocs.io/en/latest/security.html), [nh3 sanitizer options](https://nh3.readthedocs.io/en/latest/).

Charts should be generated by trusted application code from numeric assessments, never from model-provided SVG or JavaScript. Use accessible horizontal bars with a matching table. A radar chart is optional and should not replace the clearer table. Bundle all assets locally and provide print CSS.

### Report layout

1. Job, interview language/date, run ID, and report completeness.
2. Overall evidence score, with the existing explanation that it is practice evidence rather than a hiring prediction.
3. Five topic scores and five rubric dimensions, clearly distinguished. Topic scores group questions; rubric dimensions explain qualities such as relevance and specificity.
4. Three strengths and three priorities, each linked to actual answers.
5. One section per question: original question, final confirmed answer, score breakdown, evidence quote, what worked, what needs improvement, and a practical next exercise.
6. A tailored example or answer outline based on confirmed PersonalWiki facts, with explicit placeholders for missing details.
7. A short practice plan, then model/rubric provenance and any incomplete sections.

All arithmetic stays deterministic. Topic score = mean of the valid question scores in that topic under the documented rubric; show coverage such as “2/2 assessed.” Failed evaluation is unavailable, not zero. Explicit skips follow the existing documented scoring policy and are visibly labeled. Partial reports must show provisional totals and denominators. Summary models cannot alter scores, invent completed assessments, or replace missing data with a plausible value.

For practical examples, distinguish three things: a verified career fact, an interpretation of the candidate's answer, and an unverified detail the candidate must fill in. Use a structure such as situation → task → action → result, briefly explaining it when first shown. Never invent employers, years, certifications, responsibilities, metrics or outcomes. If evidence is insufficient, provide a useful outline and targeted questions rather than a fabricated polished story.

Expand the existing coaching validator deliberately. Require supporting fact IDs for factual claims and allow helpful general advice without pretending it is a profile fact. Validate quotes and references deterministically; review semantic grounding with multilingual fixtures and human review because string checks cannot prove that prose is faithful. Record the coach separately from the evaluator and never revise saved scores during a coaching retry.

## 9. Proposed file structure

Existing modules should be adapted incrementally, not moved all at once. Names below are proposed and may be adjusted during implementation.

```text
InterviewSimulator/
├── README.md                         Complete user manual
├── pyproject.toml / uv.lock           Python dependencies and exact versions
├── .env.example                      Non-secret local settings
├── scripts/
│   ├── setup.sh / setup.ps1           Platform entrypoints
│   ├── setup_environment.py          Shared guided setup
│   └── benchmark_local.py            Existing local qualification
├── config/
│   ├── model-capabilities.json       Dated compatibility evidence, no keys
│   └── download-manifest.json        Native/model versions, hashes, licenses
├── doc/
│   ├── REFINEMENT_RESEARCH_AND_IMPLEMENTATION_PLAN.md
│   ├── installation/                 OS-specific tested instructions
│   └── qualification/                Synthetic provider/voice results
├── src/interview_simulator/
│   ├── config.py / doctor.py         Profile-aware settings and readiness
│   ├── providers/
│   │   ├── base.py                   Typed provider/model contracts
│   │   ├── local.py / google.py / openai.py / anthropic.py
│   │   ├── catalog.py / capabilities.py
│   │   └── credentials.py            Server memory and approved OS vaults
│   ├── adk_runtime.py                ADK workflows and per-task models
│   ├── engine.py / storage.py        Shared states, edits, scoring snapshots
│   ├── migrations/                  Versioned, tested database migrations
│   ├── questions.py / selection.py   Validated deck and bounded adaptation
│   ├── evaluation.py / provenance.py Grounding and per-task identity
│   ├── speech.py / speech_backends/  Local platform-specific speech
│   ├── report.py / report_view.py    Markdown and safe HTML view data
│   ├── webapp.py / security.py       Local routes and protections
│   ├── static/                      JS modules, CSS tokens, local assets
│   └── templates/                   Interview shell and report template
├── agents/interview_practice/        ADK Web text interface
├── tests/                           Unit, migration, integration, browser tests
├── models/                          Ignored downloaded model assets
└── InterviewWiki/PersonalWiki/      Existing prerequisite applications
```

## 10. Phased implementation plan

Each phase has a completion gate. Design the state and security contracts in Phase 1 so Phase 3 does not invent controls that Phase 4 cannot safely support. Backend integration begins early; final release validation belongs to Phase 6.

### Phase 1 — Architecture and dependency improvements

**Objective:** establish a reproducible installation and stable contracts for providers, voice, state and documentation.

**Key tasks and approach:**

- Preserve existing local modifications and inventory the main/personal copies. Back up user state before migration work. Use synthetic fixtures for development.
- Define provider/model/task types, answer edit rules, scoring lock, migration versioning and local-only speech boundary.
- Retain ADK 2.10.0 initially; evaluate a newer 2.x only when a documented connector requirement justifies it and regression tests pass. Resolve direct SDK dependencies explicitly and update `uv.lock` deliberately.
- Implement the guided installer profiles, native/model manifest, checksum verification, project-relative paths and setup receipt. Make reruns safe.
- Qualify the three-language voice installation routes, particularly Intel Mac native builds and Windows/Linux playback. Add diagnostics that separate text-provider readiness from speech readiness.
- Rewrite the README/manual outline into verified instructions as features become available; label any unfinished commands as proposed until tested.

**Files:** `pyproject.toml`, `uv.lock`, `config.py`, `doctor.py`, `.env.example`, `scripts/setup*`, download manifest, README and installation pages.

**Dependencies:** existing uv/Python stack; optional native build tools; voice engines/assets; approved `keyring` backend. No browser build system is required for end users.

**Risks:** Intel package availability, missing OS voices, model download size, changed CLI flags, incompatible copied environments, license-specific distribution requirements.

**Tests:** clean install and rerun; paths with spaces/non-ASCII characters; interrupted download and wrong checksum; insufficient disk; absent package manager; cloud-text install with no llama/Whisper; copied project diagnostics; no private-file overwrite.

**Deliverables/gate:** installation matrix, repeatable bootstrap, configuration specification, migration design, and a documented working reference-Mac voice setup. Windows/Linux limitations remain explicit until qualified.

**Depends on:** plan approval. No implementation phase precedes this foundation.

### Phase 2 — Model provider architecture

**Objective:** support local, Google, OpenAI and Anthropic text tasks through ADK with secure credentials and discoverable compatible models.

**Key tasks and approach:**

- Implement provider contracts, server-only credential storage, profile-scoped clients and authenticated discovery with pagination/cache/refresh.
- Add compatibility metadata and synthetic connection probes. Keep unknown models visible but unqualified for scoring until their schema/adapter tests pass.
- Build and test native Gemini, local and cloud connectors with structured output. Resolve Responses-versus-Chat differences and unsupported sampling controls explicitly.
- Store immutable per-task model plans and per-call provenance. Replace the single-GGUF assumption without weakening local file verification.
- Add bounded retry/cost accounting, safe error mapping, disconnect/forget, and no-silent-fallback behavior.
- Expose a typed non-secret settings API and interactive credential CLI for ADK Web; never require a key in chat.

**Files:** new `providers/*`, capability registry, `config.py`, `adk_runtime.py`, `provenance.py`, `engine.py`, `webapp.py`, `cli.py`, ADK Web agent settings integration.

**Dependencies:** ADK-compatible provider SDK versions, `httpx`, approved keyring backend; lock all resolved versions. Avoid relying on undeclared transitive imports.

**Risks:** provider API drift, connector parameter mismatch, secret serialization, model retirement, quota versus authentication confusion, aliases changing behavior.

**Tests:** mocked provider contracts for success/401/403/429/5xx/timeout; discovery pagination/null metadata; cross-profile isolation; parameter translation; credentials absent from logs, ADK events, HTTP responses, reports and backups; blocked arbitrary endpoints; cloud run without local files; offline local run without external requests. Live tests use synthetic data, explicit keys and bounded cost.

**Deliverables/gate:** each provider completes a schema-valid synthetic ADK scoring/coaching call; model discovery and vault operations work; local-only behavior remains intact. An untested model is not labeled supported.

**Depends on:** Phase 1 contracts and dependency decisions.

### Phase 3 — Web UI/UX redesign

**Objective:** provide the confirmed Modern Minimalist interface and understandable guided setup.

**Key tasks and approach:**

- Create tokens, typography, responsive layout, localization files and reusable button/form/status components. Prefer small ES modules over a large new frontend framework.
- Build connection → models → job → readiness → interview → review/report screens, including return navigation and preserved settings.
- Add clear voice checks, model labels, data-use disclosure and optional remember-key control.
- Add interview progress, review cursor, cancellation/restart dialogs and error recovery. Wire edit/navigation controls to real shared service contracts; use disabled explanations until Phase 4 completes them.
- Show real operation states and retained input, not fake percentage progress. Implement keyboard/focus handling and local-only assets.

**Files:** `static/app.js` split as needed, new CSS/locales/UI modules, `templates/*`, UI response schemas in `webapp.py`.

**Dependencies:** existing browser platform; development-only browser automation/accessibility tooling, pinned for repeatable tests.

**Risks:** losing current voice cancellation behavior during redesign; keyboard traps; mobile scrolling; accidental exposure of provider errors or secrets; translated labels overflowing.

**Tests:** provider switching, setup/back/resume, unavailable jobs/voices, failed requests preserving answers, keyboard-only navigation, 200% zoom, narrow viewport, all three languages, contrast and screen-reader names. Screenshot checks use synthetic profiles.

**Deliverables/gate:** navigable responsive screens and approved visual examples, with working provider setup and existing text/voice functionality preserved. Do not ship nonfunctional Back/Edit/Restart controls.

**Depends on:** Phase 1 state contracts and Phase 2 settings/provider APIs; interview mutations complete in Phase 4.

### Phase 4 — Interview experience improvements

**Objective:** make question flow, answer editing, speech and recovery reliable across both interfaces.

**Key tasks and approach:**

- Implement explicit run states, read-only history, canonical answer versions, optimistic concurrency and transactional scoring snapshots.
- Add Back, edit-before-scoring, save-and-exit, cancel, restart and review commands to the shared service and ADK text interface.
- Preserve committed question IDs/order after edits and prevent selection/exposure double counting. Ensure ADK recovery honors corrected answers without replaying model side effects.
- Add optional grounded question-generation workflow and validated bank enrichment; maintain the prepared fixed fallback.
- Finish local speech adapters and recording lifecycle controls; normalize Traditional Chinese transcripts and preserve the user's reviewed wording.
- Persist operation progress independently of the browser; allow restart/reconnect without duplicate answers or grading.

**Files:** `engine.py`, `storage.py`, migrations, `adk_runtime.py`, `questions.py`, `selection.py`, `speech.py`, speech adapters, `webapp.py`, ADK agent commands and frontend controllers.

**Dependencies:** Phase 2 task models, Phase 3 UI, platform speech components qualified in Phase 1.

**Risks:** edit/scoring races, divergent ADK/database state, late canceled responses, duplicate bank statistics, migration errors, unsupported voice formats, adaptive changes that violate coverage.

**Tests:** edit question 2 after answering question 7; question 3–7 remain unchanged; report uses the new answer 2; edit rejected after scoring lock; two-tab conflicts; double submit; restart/crash at each state; unchanged bank counts on review; migration of legacy runs; real MP4/WebM clips in all languages; microphone cancellation/late permission; local audio never reaches cloud transport.

**Deliverables/gate:** complete ten-question synthetic runs in built-in UI and ADK Web, correct editable history, resumable scoring, reliable three-language voice on the reference Mac, explicit qualification results on other platforms.

**Depends on:** Phases 1–3. Provider-aware evaluation must exist before final snapshot integration.

### Phase 5 — Final report redesign

**Objective:** turn saved results into a readable assessment with useful, grounded career coaching.

**Key tasks and approach:**

- Add safe Markdown rendering, structured view data, local charts, responsive and print layouts, Markdown download and legacy report fallback.
- Calculate overall/topic/rubric scores deterministically and label coverage, skips and incomplete work correctly.
- Expand coaching schema and prompts with evidence-linked examples, missing-detail placeholders and practical exercises. Add a constrained optional overall narrative agent.
- Display evaluator/coach identity and preserve saved scores through retries. Regenerate HTML from saved validated results without re-running inference.
- Include integrity metadata for new artifacts and keep older reports viewable without fabricating missing provenance.

**Files:** `report.py`, new `report_view.py`, report templates/CSS/charts, `evaluation.py`, `adk_runtime.py`, artifact manifest handling and report routes.

**Dependencies:** qualified Markdown parser/sanitizer, optional autoescaped template engine; no remote chart service.

**Risks:** stored script injection, misleading incomplete averages, invented candidate achievements, summary/score contradictions, inaccessible charts and CJK print layout.

**Tests:** malicious Markdown/HTML/links; answer text with pipes/brackets/Unicode; partial and skipped assessments; chart/table arithmetic agreement; report re-render without model calls; fixed scores across coaching retries; grounded example fixtures in three languages; native-speaker/career-coach review of representative reports.

**Deliverables/gate:** professional HTML and portable Markdown reports with matching facts/numbers, safe rendering, useful validated coaching, and honest partial-report behavior.

**Depends on:** Phase 4 immutable scoring snapshots and Phase 2 per-task provenance.

### Phase 6 — Testing and quality assurance

**Objective:** demonstrate that the complete installation-to-report journey works and fails recoverably.

**Key tasks and approach:**

- Run lint/type checks and unit/integration/browser suites after each relevant phase, then perform the complete release matrix.
- Test clean installs and copied-project upgrades on Intel Mac, Apple Silicon, Windows and the documented Linux baseline. Virtual machines cover packaging but do not replace physical microphone/audio tests.
- Benchmark Qwen 9B and 4B separately on the reference Mac with other heavy applications closed. Record startup, memory, assessment/coaching time, schema repairs, STT time and TTS playback time. Do not benchmark them simultaneously.
- Use an evaluation set of at least 30 synthetic answer cases per language spanning weak/partial/strong evidence and missing facts. Repeat a smaller subset to measure score variation. Review translated parallels and flag language differences rather than claiming calibrated equivalence.
- Exercise provider errors, revoked keys, unavailable vaults, airplane mode, server shutdown, browser refresh, disk full, interrupted migration and partially finished reports.
- Validate README commands on clean machines. Produce a release checklist with pass/fail evidence and unresolved limits.

**Files:** existing tests plus provider, credential, migration, report-security, UI and installation suites; benchmark fixtures; CI configuration; qualification docs and README.

**Dependencies:** development test tools, target devices, synthetic fixtures, and optional bounded paid API tests. Paid tests are not required for ordinary offline CI; CI means automated checks on changes.

**Risks:** flaky external tests, uncontrolled billing, unrealistic synthetic-only quality claims, absent physical target devices, model drift after qualification.

**Tests/deliverables:** an auditable result matrix and reproducible benchmark report. All deterministic tests must pass; every advertised platform/provider path needs a completed end-to-end qualification. Clearly label a target unqualified if the required device or credential was unavailable rather than reporting a pass.

**Responsiveness targets to measure:** visual acknowledgement of a click within 200 ms; ordinary local state/readiness requests within one second at the 95th percentile while model work is running; cancel/back must not wait for an entire inference request. These are release targets, not results already achieved. Display model/transcription work separately with elapsed time and saved progress rather than extending those UI targets to CPU-heavy tasks.

**Depends on:** integrated Phases 1–5, with targeted tests already accumulated throughout development.

## 11. Release gates and migration safety

| Gate | Evidence required |
|---|---|
| Existing behavior | Current offline tests, ADK contracts, voice cancellation, wiki read-only protections and report integrity still pass |
| Installation | A fresh user follows the manual without hidden files or an existing `.venv`; cloud-text profile needs no local model |
| Provider isolation | No key leakage; local mode makes no cloud calls; every selected cloud task contacts only its selected provider |
| Correct edits | Previous answers can change before scoring; existing question order stays intact; scoring cannot race an edit |
| Durable results | Crash/retry preserves completed scores; missing work is explicit; a new run cannot overwrite another run's report |
| Report security | Script/unsafe-link fixtures cannot execute; charts and Markdown show the same valid values |
| Language quality | Readable English/Japanese/Traditional Chinese; no unsupported career claims in reviewed fixtures; remaining score-calibration limits disclosed |
| Usable UI | Fast local feedback, accessible controls, clear failures, retained drafts, no silent voice buttons |
| Platform claims | Real installation/audio evidence for each advertised OS/language combination |

Suggested deterministic developer commands, using the project's installed environment:

```sh
uv run ruff check .
uv run mypy src/interview_simulator
uv run pytest -m "not model and not hardware"
node tests/browser_state.cjs
node tests/browser_voice.cjs
```

Extend these with the new pinned browser suite during implementation. Live model and hardware checks run separately so their resource use does not distort timings. Do not claim the new plan passed runtime tests: this planning task changes documentation only.

Before database migration, create a verified backup of application and ADK state. Use numbered, transactional migrations and test upgrade plus recovery from a failed migration. Keep legacy reports and their original manifests unchanged. Existing runs without a per-task model plan retain legacy local behavior; completed runs are never retroactively regraded or assigned invented provenance.

Develop in the main InterviewSimulator project first. Transfer reviewed code/dependency changes to PersonalInterviewSimulator without overwriting its `.env`, wiki, job folders, models, databases, or reports. Recreate environments as needed and run migration/readiness checks on the copy. Avoid bulk directory replacement or bulk Git staging of private data.

The plan incorporates all four clarified product decisions. Remaining uncertainties are implementation qualification items—particularly provider connector compatibility and Windows/Linux local voices—not unanswered choices about cloud audio, key storage, edits, or theme. After approval, Phase 1 is the starting point.
