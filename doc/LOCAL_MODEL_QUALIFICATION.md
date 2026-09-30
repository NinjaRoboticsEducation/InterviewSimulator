# Local model qualification on the reference Mac

30 September 2026

This is a small, reproducible **synthetic** check of the two recommended local models. It does not use PersonalWiki data or a real job package. It measures report-generation work, not the time to display the next fixed interview question. Both models passed the application's JSON, quoted-answer, language-script, and model-file checks in these samples. That is useful evidence that they run locally, but it is not a guarantee of fair scores or good advice for real candidates.

## Test conditions

- Device: 2018 Mac mini, 3 GHz six-core Intel Core i5, 32 GB RAM, macOS Sequoia 15.7.9. The user had paused other applications to free resources.
- Runtime: local `llama-server`, CPU only (`-ngl 0`, six threads), context 4096, one model loaded at a time; application uses Google ADK 2.x through the loopback endpoint.
- Models: Qwen3.5-9B Q4_K_M (`SHA-256 03b74727…a853daf52b7e8`) and Qwen3.5-4B Q4_K_M (`SHA-256 00fe7986…d1fb69ef11a4`). Full fingerprints appear in the README and are checked by the application at runtime.
- Workload: one short, equivalent synthetic portfolio answer each in English, Japanese, and Traditional Chinese, assessed against the same English job requirement. English also received one coaching example. Timings are wall-clock seconds for each application call and include ADK overhead; model-file identification time is shown separately.
- Method: `scripts/benchmark_local.py`. Each locale was sampled once. No competing heavy test suite ran during either model benchmark.

| Model | File identification | English assessment | English coaching | Japanese assessment | Traditional Chinese assessment |
|---|---:|---:|---:|---:|---:|
| 4B Q4_K_M | 6.61 s | 50.20 s | 42.52 s | 44.27 s | 31.19 s |
| 9B Q4_K_M | 16.68 s | 77.25 s | 65.20 s | 59.13 s | 49.61 s |

The 9B server also needed about 99 seconds to load and announce readiness on this machine; that startup is separate from the table. In the English example, assessment plus coaching took **92.72 seconds with 4B** and **142.45 seconds with 9B**. A full ten-answer report can therefore take many minutes, especially if a request needs repair or an answer is longer. A score is generated after the interview; question delivery itself uses the prepared package and does not wait for scoring.

## What the output showed

| Check | 4B | 9B |
|---|---|---|
| All three assessment calls completed | Yes | Yes |
| Exact answer quote validated | Yes, all three | Yes, all three |
| Feedback in requested language/script | Yes, all three | Yes, all three |
| English coaching example included the supplied confirmed fact and visible fill-in prompts | Yes | Yes |
| Score for English / Japanese / Traditional Chinese equivalent examples | 46.2 / 35.0 / 61.2 | 48.8 / 37.5 / 58.8 |

The 9B English feedback named the candidate's actions and honesty more specifically. The 4B English “strength” was only “Partial,” which is too terse to help someone improve. Both models produced substantially different scores for translated versions of roughly the same answer. The answers are not byte-for-byte translations, the job requirement stayed in English, and this is only one trial, so these figures do **not** establish the size or source of a language bias. They do show that a qualification score must be presented as practice feedback, never as a hiring prediction or a calibrated cross-language comparison. The report already labels it as evidence demonstrated in that session. Do not compare scores across interview languages as if they share a validated scale.

The confirmed-fact coaching example remained grounded, but it contains bracketed prompts for details the candidate must verify. It is a practice outline rather than a ready-to-recite answer. A native speaker and a career coach still need to review full ten-answer reports from real, consented sample profiles before this can be described as professionally validated coaching.

## Operational recommendation

Keep **9B Q4_K_M as the quality-first default** when its roughly one-minute-per-assessment response is acceptable. Choose **4B Q4_K_M** if the report wait is too long or memory pressure appears. Start a new run after changing models; the application binds saved assessments to the file fingerprint and will refuse to mix different model files inside one report. Both models are usable for turn-by-turn practice because the next prepared question is presented without waiting for the report model.

For reproducibility, run `python scripts/benchmark_local.py <model.gguf> <output.json>` from an installed project environment while the corresponding `llama-server` is running on the configured loopback endpoint. The script uses only hard-coded synthetic answers. Keep the generated JSON outside the project if you do not want benchmark artifacts in your copy. These measurements should be repeated on each target device and with representative answers before setting a timeout or performance promise.
