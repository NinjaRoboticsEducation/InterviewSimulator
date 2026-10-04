# README review and Homebrew diagnosis

Reviewed on 4 October 2026: `README.md`, `README_jp.md`, `README_tc.md`, and `README_cn.md`.

## Result

The translations preserve the project's general purpose and workflow, but all four shared several technical omissions. They have been corrected while retaining the user's section structure. Application code, lockfiles, personal data, and installed toolchains were not changed. This review updates the InterviewSimulator documentation; it does not overwrite the personal installation's documentation or run an installer.

## Homebrew diagnosis

The observed command was `brew install openssl@3 rust pkgconf`. Its process tree showed `cmake --build build`, Ninja, and active Apple Clang compiler workers under LLVM 23.1.2. The log continued growing and the main build counter advanced from `[7174/9135]` to `[7542/9135]`. This was an active source compilation, not a confirmed hang. Earlier counters referred to a nested runtime build and must not be treated as overall progress. The inspected system reported Intel x86_64 and macOS 15.8.1; the README's 15.7.9 reference describes the previous tested configuration.

Two separate dependency decisions explain the delay:

1. `uv.lock` pins `cryptography 50.0.1`; all its recorded macOS wheels are ARM64, so an uncached Intel installation needs to compile it. Rust/OpenSSL prerequisites therefore remain relevant, including cloud-only profiles.
2. Homebrew's current Rust formula depends on LLVM. Intel macOS is now Tier 3 and current prebuilt packages are generally unavailable, so Homebrew may build large compiler dependencies from source. Requesting Homebrew Rust is a costly route to obtaining the tool needed for a much smaller Python package build.

Local Homebrew metadata also listed Rust 1.98.1, OpenSSL 3.6.5, and pkgconf 3.0.7 as installed. `rustc` and `cargo` were absent from this inspection shell's PATH, but the existing Cellar executables ran successfully by absolute path. `pkg-config` initially could not locate OpenSSL even though its `.pc` file existed. This supports checking executable discovery and setting `OPENSSL_DIR`/`PKG_CONFIG_PATH`, rather than assuming a complete toolchain upgrade is necessary. The ongoing Homebrew operation may change links during installation; do not repair links concurrently with it.

The corrected [Intel Mac guide](installation/INTEL_MAC_SETUP.md) recommends reusing working tools, using the official rustup binary installer when Rust is missing, installing only missing OpenSSL/pkgconf packages, and exporting OpenSSL's location in the terminal running setup. It explains how to monitor progress or stop the current installation with Ctrl+C before switching routes. No package downgrade or checksum bypass is recommended.

The Homebrew job was left running. No system package installation, removal, relinking, or cancellation was performed.

## Corrections made

| Issue | Correction |
|---|---|
| All translated English links pointed to nonexistent `README_en.md` | Pointed to `README.md`. |
| Intel prerequisites unconditionally prescribed Homebrew Rust | Explained the current lockfile requirement and linked the existing-tools/rustup route; updated the linked native-voice guide too. |
| macOS Git instructions introduced another Homebrew install | Use Apple command-line tools when needed; skip if Git already works. |
| Step 3 used `cd InterviewWiki` while still in PersonalWiki | Use `cd ..`; explicitly return to the root before simulator commands. |
| Fresh-machine dry-run assumed Python already existed | Explain the prerequisite and an explicit uv-managed Python preview command. |
| Windows/local voice profile appeared fully automatic | Explain CMake/C++/FFmpeg prerequisites and separate voice setup. |
| Manual download examples hid platform differences | Add PowerShell directory/download guidance and per-platform checksum commands; use curl HTTP-failure handling. |
| One macOS-only voice-test path, then instructions to reuse it | Use three distinct relative filenames, since voice-test refuses overwrites. |
| `verify-run <run-id>` could be pasted as shell redirection | Use the `RUN_ID` placeholder. |
| ADK cloud start omitted provider setup and explicit consent | Document saved model settings, `--allow-cloud-text`, secure key loading, and `cloud-ok`. |
| Recording extensions, countdown, 6,000-character limit, and history relocation were omitted | Restore concise descriptions in every language. |
| Translations said answers lock after report completion | Clarify that locking happens when generation starts. |
| `report.md` implied the first version was always current/final | Explain immutable `report-rNN.md` versions, ten required examples, and resumable drafts. |
| Absolute guarantee that AI never invents achievements | Explain evidence checks and the need for user verification. |
| Backup/migration omitted stopped-server requirement and history databases | Explain server shutdown, backup scope, separate source-wiki copying, and restore before first server start. |
| Ollama cloud/local and Chinese documentation/runtime languages were ambiguous | Clarify local Ollama does not inherently require a cloud key; Simplified Chinese is documentation only. |
| Ten GB suggested a safe total installation budget | Warn that caches and source builds need extra space; no fixed total guarantee. |
| Mermaid labels used unquoted literal newline escapes | Use quoted labels with explicit line breaks. |

## Remaining packaging observations

- The setup script still **prints** the older Homebrew Rust suggestion. It does not run that command automatically. The new Intel guide explicitly explains the discrepancy. A future installer refinement should align the message and add prerequisite detection before Python synchronization.
- `scripts/build_release.py` currently includes only `README.md` in its top-level file allowlist. The three translations must be added there before using that helper to distribute a multilingual source bundle. A normal Git clone includes them once committed; the helper omission does not affect Git cloning.
- The three new translations and `doc/README_bak.md` were untracked at review time. No commit or push was performed. Treat the backup README as historical, since it retains superseded guidance.

These are disclosed separately because the requested work was documentation review and installation diagnosis, not an installer/dependency redesign.

## Validation and limits

Checked every local Markdown link in the four READMEs and the two installation guides, balanced code fences, syntax of the README shell blocks without executing them, all model URLs/checksums against the checked-in manifest, required cloud-consent/recording explanations, and corrected directory transitions. `git diff --check` passed. Commands were also compared with the CLI parsers, setup scripts, report naming logic, and backup implementation.

No fresh installation was run and no models were downloaded. The source checkout did not have a `.venv` at review time. No full application tests or physical voice tests were needed for these documentation-only changes. Windows command guidance was inspected, not executed on Windows. Mermaid source was corrected but not visually rendered during this review.

Vendor references:

- [Homebrew support tiers](https://docs.brew.sh/Support-Tiers)
- [Homebrew Rust formula](https://formulae.brew.sh/formula/rust)
- [Cryptography 50.0.1 installation](https://cryptography.io/en/50.0.1/installation/)
- [Rustup installation](https://rust-lang.github.io/rustup/installation/index.html)
