# Intel Mac setup and the Homebrew LLVM build

Checked on 4 October 2026. These instructions apply to Intel (`x86_64`) macOS, including the project's 2018 Mac mini. Run `uname -m` to check your architecture. Apple Silicon has different prebuilt-package availability.

## Why the install can look stuck

The project's lockfile selects `cryptography 50.0.1`. Its recorded macOS wheels are ARM64 only, so a fresh Intel installation builds this Python dependency from source unless a compatible built wheel is already cached. Cloud-only mode still installs the same Python dependencies.

That build needs Apple command-line tools, Rust, and OpenSSL. However, installing **Rust through Homebrew** also introduces its LLVM dependency. LLVM is a large compiler toolchain. Homebrew currently places Intel macOS in Tier 3, where current binary packages are not generally provided. A command such as `brew install openssl@3 rust pkgconf` can therefore compile LLVM and Rust locally. This can take hours and substantial disk space; it is not an InterviewSimulator model download or interview task.

`==> cmake --build build` is a normal build-stage message. Homebrew may leave that line on screen while compiler output goes to a log. It is not by itself evidence of a hang. In another terminal, inspect:

```sh
tail -n 5 "$HOME/Library/Logs/Homebrew/llvm/02.cmake.log"
```

Open Activity Monitor and look for `clang`, `clang++`, or `ninja` using CPU. Changing log sizes and new compilation steps indicate progress. Counts like `[7174/9135]` describe one build, not the entire Homebrew transaction; nested builds have their own counts. They cannot give a reliable overall completion time.

You can let an active build finish. If you choose to avoid this route, press **Ctrl+C once in the terminal running Homebrew**, and wait for it to return to the prompt before starting another install. Do not run a second installer or delete its temporary build directory while the first is active. Stopping may discard progress, so a later retry can rebuild work.

## Prefer existing tools, then Rust's binary installer

First check whether the necessary tools already work:

```sh
xcode-select -p
clang --version
command -v rustc cargo pkg-config
rustc --version
cargo --version
brew list --versions openssl@3 pkgconf rust
```

A missing command is a useful diagnostic here, not a reason to repeat the whole Homebrew installation. A formula listed as installed may still be unlinked or absent from your terminal's `PATH`, particularly during an upgrade. Resolve the active installation first. Reuse a working Rust toolchain that meets the locked package's requirements; do not upgrade it solely because it is not the newest. Cryptography 50.0.1 documents Rust 1.83.0 as its minimum.

If Apple's tools are missing:

```sh
xcode-select --install
```

Complete the installation dialog before proceeding. Do not reinstall the tools if `xcode-select -p` and `clang --version` already work.

If Rust is missing, use the Rust project's official installer. This downloads a compiled toolchain instead of building Homebrew's LLVM dependency:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- --profile minimal
. "$HOME/.cargo/env"
rustc --version
cargo --version
```

Review the installer's prompts. If it detects an existing Rust installation, follow its coexistence guidance rather than forcing an overwrite. Open a new terminal if needed. Do not mix the Homebrew and rustup executables accidentally; `command -v rustc cargo` shows which ones will run.

Install **only missing** OpenSSL/pkgconf packages. When both are missing:

```sh
brew install openssl@3 pkgconf
```

This can still compile those smaller packages on Intel, but does not request Homebrew's Rust/LLVM dependency chain. Homebrew is not guaranteed to provide binary packages for this Mac. The linked native-tool guide covers manual inference-tool builds; those are separate from Python's cryptography build.

In the same terminal that will run setup, make OpenSSL discoverable:

```sh
export OPENSSL_DIR="$(brew --prefix openssl@3)"
export PKG_CONFIG_PATH="$OPENSSL_DIR/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
pkg-config --modversion openssl
```

These are shell build settings, **not entries in the application's `.env` file**. The setup subprocesses inherit them. If you reopen the terminal before setup, set them again. Apple's bundled TLS libraries are not a substitute for the required OpenSSL installation.

From the InterviewSimulator project root, choose your desired profile, for example:

```sh
sh scripts/setup.sh --profile cloud-text
```

Or, for Qwen plus local voice:

```sh
sh scripts/setup.sh --profile local-voice --model 9b --install-native
```

Do not run both merely to follow the example. Local voice additionally needs llama.cpp, whisper.cpp, FFmpeg, and language voices; see [the native-tool guide](LOCAL_VOICE_SETUP.md). The current setup script's Intel reminder may still mention `brew install ... rust ...`; use the route above instead. The setup script itself only prints that Rust reminder; it does not execute that command automatically.

Keep the lockfile. Do not downgrade a security dependency or bypass checksum checks to avoid a compiler requirement. A Python-version change alone does not supply an Intel wheel when the locked release has none.

## Verification limits

The diagnosis used the running Homebrew process tree, advancing LLVM logs, local formula metadata, and the repository lockfile. The rustup route follows official vendor instructions. This review did not install or replace system toolchains, finish a fresh app installation, or benchmark models. Package availability can change; recheck when updating the lockfile.

Sources:

- [Homebrew support tiers](https://docs.brew.sh/Support-Tiers)
- [Homebrew Rust formula and dependencies](https://formulae.brew.sh/formula/rust)
- [Cryptography 50.0.1 build requirements](https://cryptography.io/en/50.0.1/installation/)
- [Official rustup installation guide](https://rust-lang.github.io/rustup/installation/index.html)
- [Rust's macOS platform support](https://doc.rust-lang.org/rustc/platform-support/apple-darwin.html)
