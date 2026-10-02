# Local model and voice installation

Checked: 1 October 2026. The project keeps audio local regardless of your text-model provider. A text-only installation does not require any speech tools.

## What is installed where

| Component | Required for | Installed by |
|---|---|---|
| uv and Git | Environment setup and source checkout | Initial vendor installation |
| Python 3.13 and locked packages | Every profile | `scripts/setup.sh` / `scripts/setup.ps1` |
| llama-server | Local text inference | Homebrew or pinned CMake source build |
| Qwen3.5 GGUF | Local text inference | Setup model manifest, 9B first / 4B alternative |
| FFmpeg | Decode browser recordings; convert macOS speech output | Platform package manager or official Windows build |
| whisper-cli | Local speech recognition | Homebrew or pinned CMake source build |
| Multilingual whisper small | English, Japanese and Mandarin recognition | Setup manifest, approximately 488 MB |
| macOS `say` voices | macOS speech playback | macOS voice download settings |
| System.Speech voices | Windows speech playback | Windows installed voices, enumerated by this adapter |
| Piper and voice assets | Optional local English/Mandarin playback | Separate isolated Python environment and licensed voice downloads |
| Open JTalk, dictionary and HTS voice | Optional local Japanese playback | Distribution packages or official source |

The setup profiles choose which downloads and tools are necessary. Native binaries installed under `.native/<tool>/build/bin` are discovered by the application on each device. Python environments and native binaries must be rebuilt after moving devices. Source pins and model checksums are in `config/download-manifest.json`. Package-manager builds may be newer than the source-build pins; run the model and speech checks after an update.

## macOS

Before Python setup on Intel Mac, install Apple’s command-line tools and run `brew install openssl@3 rust pkgconf`. The locked cryptography dependency builds from source on this device, independently of the local voice profile. [Official build instructions](https://cryptography.io/en/latest/installation/#building-cryptography-on-macos).

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Homebrew](https://brew.sh/) using their official instructions. For source builds, install Apple's command-line development tools with `xcode-select --install`.
2. In the project folder, run:

   ```sh
   sh scripts/setup.sh --profile local-voice --model 9b --dry-run
   sh scripts/setup.sh --profile local-voice --model 9b --install-native
   ```

   This installs missing Homebrew packages `llama.cpp`, `whisper.cpp`, and `ffmpeg`, the locked Python applications, Qwen 9B, and multilingual whisper small. Use `--profile cloud-local-voice` to omit Qwen and llama.cpp. Homebrew availability on an older Intel OS can change; if a formula cannot be built, install the pinned source route below rather than assuming an old package supports Qwen3.5.
3. Open System Settings → Accessibility → Spoken Content. Download an English, Japanese, and Mandarin voice. [Apple's voice instructions](https://support.apple.com/en-lb/guide/mac-help/mchlp2290/mac) explain the download controls. Voice assets may require internet during installation; runtime synthesis is local.
4. List installed names:

   ```sh
   say -v '?'
   ```

   The app prefers Samantha (`en_US`), Kyoko (`ja_JP`), and Meijia (`zh_TW`) when present. If your names differ, set these in the private `.env`:

   ```dotenv
   INTERVIEW_SIMULATOR_TTS_BACKEND=auto
   INTERVIEW_SIMULATOR_VOICE_EN=Samantha
   INTERVIEW_SIMULATOR_VOICE_JA=Kyoko
   INTERVIEW_SIMULATOR_VOICE_ZH_HANT=Meijia
   ```

5. Restart the application, run `doctor`, and generate/play the three samples below. A voice being listed does not prove your speaker or browser playback is working.

## Windows

1. Install uv, Git, [CMake](https://cmake.org/download/), and Microsoft's C++ build tools. Use a Developer PowerShell so CMake can find the compiler. Install FFmpeg from the [official download links](https://ffmpeg.org/download.html), add its `bin` directory to the user's `PATH`, and reopen the terminal. Verify `ffmpeg -version`.
2. From the project root:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Profile local-voice -Model 9b -DryRun
   powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Profile local-voice -Model 9b -InstallNative
   ```

   The script can build pinned llama-server and whisper-cli sources when Git, CMake and the compiler are available. It does not silently install a compiler or choose a third-party FFmpeg executable. A missing native tool produces exit code 2 after Python setup. Supply the missing tool and rerun.
3. Install local English, Japanese and Mandarin speech voices through Windows language/speech settings. The adapter uses Windows PowerShell and .NET **System.Speech**, not a cloud speech API. Only voices returned by its `GetInstalledVoices()` call are available; a voice visible in another Windows speech API may not appear here. [Microsoft's API description](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer?view=net-8.0) explains voice enumeration and selection.
4. Run `uv run interview-simulator doctor` and inspect `speech.windows_voices`. If necessary, choose exact enumerated names:

   ```dotenv
   INTERVIEW_SIMULATOR_TTS_BACKEND=windows
   INTERVIEW_SIMULATOR_WINDOWS_VOICE_EN=<installed English voice name>
   INTERVIEW_SIMULATOR_WINDOWS_VOICE_JA=<installed Japanese voice name>
   INTERVIEW_SIMULATOR_WINDOWS_VOICE_ZH_HANT=<installed Mandarin voice name>
   ```

   Do not copy those placeholders literally. The auto backend also selects matching languages when available. Installing a Windows language pack does not guarantee System.Speech coverage: use Piper for a verified available voice, or keep that language's practice typed until it is configured.
5. Generate samples to a new path under an existing directory, such as `C:\Temp\interview-ja.wav`. This adapter has mocked contract tests but still needs physical three-language testing on your Windows device.

## Linux

For Debian/Ubuntu, install the build prerequisites and FFmpeg:

```sh
sudo apt-get update
sudo apt-get install ffmpeg git cmake build-essential
sh scripts/setup.sh --profile local-voice --model 9b --install-native
```

The source-build installer pins llama.cpp and whisper.cpp versions. On other distributions, use your distribution's equivalent build packages and FFmpeg, then the same setup script. The automated package-manager route assumes `apt-get`.

English and Mandarin can use **Piper**, a local speech synthesizer. Follow the maintained [OHF Piper installation guide](https://github.com/OHF-Voice/piper1-gpl) and [voice instructions](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md). The old rhasspy project is not the installation authority. Keep Piper in its own environment to avoid changing the main application lockfile:

```sh
uv venv .voice-piper
uv pip install --python .voice-piper/bin/python piper-tts
```

Make that environment's `piper` executable available on `PATH` when starting the simulator, for example:

```sh
export PATH="$PWD/.voice-piper/bin:$PATH"
```

Choose licensed English and Mandarin models from the maintained voice catalog, download each `.onnx` model **and its matching `.onnx.json`**, and place them under your project's `models/voices/` folder. Model availability and licenses vary; no TTS model is bundled. Set the exact filenames in `.env`:

```dotenv
INTERVIEW_SIMULATOR_TTS_BACKEND_EN=piper
INTERVIEW_SIMULATOR_TTS_BACKEND_ZH_HANT=piper
INTERVIEW_SIMULATOR_PIPER_MODEL_EN=models/voices/<English voice>.onnx
INTERVIEW_SIMULATOR_PIPER_MODEL_ZH_HANT=models/voices/<Mandarin voice>.onnx
```

A Mandarin model's pronunciation of Traditional Chinese must be tested. The application does not alter your saved answers into Simplified Chinese. Do not assume Piper supplies a project-qualified Japanese voice.

For Japanese, the application has an **Open JTalk** adapter. Install the engine, a UTF-8 dictionary, and a licensed HTS voice using your distribution packages or the [official project](https://open-jtalk.sp.nitech.ac.jp/). Check the paths supplied by your package manager; dictionaries and voices are separate assets. Set:

```dotenv
INTERVIEW_SIMULATOR_TTS_BACKEND_JA=open-jtalk
INTERVIEW_SIMULATOR_OPENJTALK_DICTIONARY=/actual/path/to/utf8-dictionary
INTERVIEW_SIMULATOR_OPENJTALK_VOICE=/actual/path/to/Japanese.htsvoice
```

The adapter sends text on stdin and uses `-x`, `-m`, and `-ow` for dictionary, voice and output. It is not physically qualified on Linux here; verify real playback, pronunciation, and microphone recognition before relying on the setup. Text interviews remain available while you configure speech.

## Manual pinned inference builds

For an environment without Homebrew packages, use the references recorded in the manifest. The following mirrors the current pins:

```sh
git clone --depth 1 --branch b10621 https://github.com/ggml-org/llama.cpp.git .native/llama-server
cmake -S .native/llama-server -B .native/llama-server/build -DCMAKE_BUILD_TYPE=Release
cmake --build .native/llama-server/build --config Release --parallel 2 --target llama-server

git clone --depth 1 --branch v1.7.6 https://github.com/ggml-org/whisper.cpp.git .native/whisper-cli
cmake -S .native/whisper-cli -B .native/whisper-cli/build -DCMAKE_BUILD_TYPE=Release
cmake --build .native/whisper-cli/build --config Release --parallel 2 --target whisper-cli
```

Windows uses the same CMake arguments from Developer PowerShell. Inspect build failures rather than suppressing them. Do not mix a build from another processor/OS with the destination environment. The reference Intel model tests use CPU inference; acceleration and driver support need separate testing.

## Confirm that voice actually works

At the root, with `.env` configured and the Python dependencies installed:

```sh
uv run interview-simulator doctor
uv run interview-simulator voice-test /private/tmp/interview-en.wav --locale en
uv run interview-simulator voice-test /private/tmp/interview-ja.wav --locale ja
uv run interview-simulator voice-test /private/tmp/interview-zh.wav --locale zh-Hant
```

Use `/tmp/...` on Linux or `C:\Temp\...` on Windows. Choose a new filename each time; this command refuses to overwrite existing audio. Play each file. For a local speech-recognition check:

```sh
uv run interview-simulator transcribe /path/to/your-short-recording.wav --locale ja
```

Then use the built-in browser to test the complete route: allow microphone access for the local address, record a short answer, stop, correct the text, and confirm it. Audio is limited to 20 MB and three minutes; recognition runs locally and may take time on an Intel CPU. The browser shows permission, recording, transcription and playback progress. Stop audio / cancel terminates browser playback and releases microphone tracks; a native operation already processing finishes under its timeout before the CPU queue is released.

If recognition is wrong, review the text instead of accepting it automatically. A software-generated sample is useful for wiring checks, but does not establish accuracy for your accent, room or microphone.
