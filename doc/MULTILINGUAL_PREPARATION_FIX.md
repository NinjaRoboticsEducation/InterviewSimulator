# Japanese and Traditional Chinese preparation fix

Checked: 6 October 2026.

## Root cause

The saved preparation records show successful English preparation and failed Japanese/Traditional Chinese translation tasks with both local Qwen and Ollama. Offline replay identified a deterministic validator error: translating an English month name into a numeric month introduced a number the old check did not recognize in the original. For example, `August 2021` and `2021年8月` describe the same date, but the previous check compared `{2021}` with `{2021, 8}` and rejected the translation.

Eight recorded responses that failed specifically because of this date conversion now pass unchanged. Personal text was replayed locally; it was not uploaded or copied into public tests or this report.

Other saved responses retained whole English career descriptions inside Japanese or Chinese questions. Those remain invalid. The repair prompt previously supplied only the validation error; it now includes the rejected response and explicit guidance to translate quoted descriptions, job titles, and geographic wording while retaining protected names and acronyms.

## Changes

- Normalize explicit English full/abbreviated month names and numeric date forms before comparing quantities. Support month/year and common day-first/month-first date formats.
- Compare year/month/day associations as well as numeric values. A swapped month or changed year still fails; an unrelated name such as “May” does not become a number.
- Keep the existing language, untranslated-passage, placeholder, and quantity checks. Repair remains bounded to one extra attempt; provider outages do not become translation-repair loops.
- Version the translation cache as `question-localization-v2`; old cache entries are not used for new preparations. Corrupt or invalid current cache entries are regenerated on an explicit preparation attempt. Existing reports and delivered question history are not rewritten.
- Record safe translation-stage reason codes and question ordinals without putting personal text into error messages. Both interfaces share the same corrected preparation engine; the built-in interface explains translation failures in English, Japanese, and Traditional Chinese.

## Validation

- Full source suite: 194 tests passed before adding three additional cache-damage cases.
- Final focused preparation suite: 21 tests passed, including those three cache cases, all three languages, fixed and generated decks, repair exhaustion, and rejection of changed dates.
- Saved-response replay: all eight previously rejected month conversions pass; genuine untranslated passages still fail.
- Live local Qwen3.5-9B Q4_K_M: fictional dated-profile questions passed in English, Japanese, and Traditional Chinese. The check used isolated temporary state and no cloud calls.
- Both JavaScript suites passed in both copies. Python lint, formatting, and whitespace validation passed; type checking found no issues in 34 application files.
- After deployment, the personal copy passed 60 preparation and multilingual tests. All eight deployed files match the source copy. Hash checks confirmed that 515 protected personal files, including both interview databases, remained unchanged. Private database/code backups are under `.simulator/maintenance/multilingual-preparation-20261006`.

The automated full-deck tests use controlled model responses. The live test checks one representative dated question per language, not an entire live interview for every provider. Ollama responses were replayed offline; no new cloud requests or charges were made. The model may still produce invalid output occasionally; the app preserves failed preparation for explicit retry or native fixed questions instead of silently accepting it.

## Use after updating

The simulator and llama.cpp servers are stopped after validation. Restart the selected model server if using local text, then restart the personal simulator and reload its page. For a failed, uncancelled preparation, choose Resume and then Retry preparation. Cancelled test runs remain cancelled; start a new practice for those. If another interview is active, resume it or explicitly cancel it before starting a different run. Reconnect a session-only provider key if necessary.

No saved interviews, answers, reports, candidate facts, job packages, or provider settings are deleted by this fix. No dependency versions are changed.
