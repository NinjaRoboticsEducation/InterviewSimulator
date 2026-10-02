from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

from .local_voices import asset_path, jtalk_ready, speak_jtalk, windows_call, windows_voice
from .processes import run as run_process

LANGUAGE = {"en": "en", "ja": "ja", "zh-Hant": "zh"}


@lru_cache(maxsize=1)
def installed_voices() -> dict[str, str]:
    if not shutil.which("say"):
        return {}
    try:
        result = run_process(["say", "-v", "?"], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {}
    return {
        match[1].strip(): match[2]
        for line in result.stdout.splitlines()
        if (match := re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#", line))
    }


def selected_voice(locale: str) -> str | None:
    configured = os.environ.get(f"INTERVIEW_SIMULATOR_VOICE_{locale.replace('-', '_').upper()}")
    if configured:
        return configured
    voices = installed_voices()
    preferred = {"en": ("Samantha", "en_US"), "ja": ("Kyoko", "ja_JP"), "zh-Hant": ("Meijia", "zh_TW")}
    name, language = preferred[locale]
    if name in voices:
        return name
    return next((voice for voice, tag in voices.items() if tag == language), None)


class Speech:
    """Local whole-turn recognition and speech. Requires user-installed native assets."""

    def __init__(self, model_path: Path | None = None):
        configured = os.environ.get("INTERVIEW_SIMULATOR_WHISPER_MODEL")
        root = Path(__file__).resolve().parents[2]
        configured_path = root / Path(configured).expanduser() if configured else None
        default = root / "models/whisper/ggml-small.bin"
        self.model_path = model_path or configured_path or (default if default.is_file() else None)

    def capabilities(self) -> dict[str, object]:
        voices = {locale: selected_voice(locale) for locale in LANGUAGE}
        piper_models = {
            locale: asset_path(
                os.environ.get(f"INTERVIEW_SIMULATOR_PIPER_MODEL_{locale.replace('-', '_').upper()}")
            )
            for locale in LANGUAGE
        }
        windows_voices = {locale: windows_voice(locale) for locale in LANGUAGE}
        status: dict[str, object] = {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "whisper_cli": bool(shutil.which("whisper-cli")),
            "whisper_model": bool(self.model_path and self.model_path.is_file()),
            "mac_say": bool(shutil.which("say")),
            "piper": bool(shutil.which("piper")),
            "configured_voices": voices,
            "configured_piper_models": {
                locale: str(value) if value else None for locale, value in piper_models.items()
            },
            "windows_voices": windows_voices,
            "open_jtalk_ready": jtalk_ready(),
        }
        status["asr_ready"] = bool(status["ffmpeg"] and status["whisper_cli"] and status["whisper_model"])
        status["mac_tts_ready"] = bool(status["ffmpeg"] and status["mac_say"] and all(voices.values()))
        status["piper_tts_ready"] = bool(
            status["piper"]
            and all(
                value and Path(value).is_file() and Path(str(value) + ".json").is_file()
                for value in piper_models.values()
            )
        )
        by_language = {}
        for locale in LANGUAGE:
            backend = self.backend(locale)
            mac_ready = bool(status["ffmpeg"] and status["mac_say"] and voices[locale])
            model = piper_models[locale]
            piper_ready = bool(
                status["piper"] and model and model.is_file() and Path(str(model) + ".json").is_file()
            )
            windows_ready = bool(windows_voices[locale])
            japanese_ready = locale == "ja" and jtalk_ready()
            options = {
                "say": mac_ready,
                "piper": piper_ready,
                "windows": windows_ready,
                "open-jtalk": japanese_ready,
            }
            by_language[locale] = any(options.values()) if backend == "auto" else options.get(backend, False)
        status["tts_by_language"] = by_language
        status["tts_ready"] = all(by_language.values())
        return status

    def transcribe(self, audio: bytes, locale: str) -> str:
        return self._transcribe(audio, locale, clip=False)[0]

    def transcribe_segment(self, audio: bytes, locale: str) -> dict:
        text, limited = self._transcribe(audio, locale, clip=True)
        return {"text": text, "limited": limited, "limit_seconds": 180}

    def _transcribe(self, audio: bytes, locale: str, *, clip: bool) -> tuple[str, bool]:
        limited = False
        if locale not in LANGUAGE or not 0 < len(audio) <= 20_000_000:
            raise ValueError("Unsupported language or recording size")
        if not self.model_path or not self.model_path.is_file():
            raise RuntimeError("Configure a local whisper.cpp model before using voice input")
        if not shutil.which("ffmpeg") or not shutil.which("whisper-cli"):
            raise RuntimeError("ffmpeg and whisper-cli must be installed locally")
        with tempfile.TemporaryDirectory(prefix="interview-speech-") as directory:
            root = Path(directory)
            source = root / "answer.webm"
            wav = root / "answer.wav"
            source.write_bytes(audio)
            run_process(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-format_whitelist",
                    "wav,matroska,webm,ogg,mov,mp3,flac,aac",
                    "-i",
                    str(source),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-t",
                    "181",
                    str(wav),
                ],
                check=True,
                capture_output=True,
                timeout=45,
            )
            with wave.open(str(wav), "rb") as decoded:
                if decoded.getnframes() / decoded.getframerate() > 180:
                    if not clip:
                        raise ValueError(
                            "Recording exceeds three minutes; shorten it or enter a typed answer"
                        )
                    limited = True
                    params = decoded.getparams()
                    frames = decoded.readframes(180 * decoded.getframerate())
            if limited:
                with wave.open(str(wav), "wb") as trimmed:
                    trimmed.setparams(params)
                    trimmed.writeframes(frames)
            run_process(
                [
                    "whisper-cli",
                    "-m",
                    str(self.model_path),
                    "-f",
                    str(wav),
                    "-l",
                    LANGUAGE[locale],
                    "-nt",
                    "-otxt",
                    "-of",
                    str(root / "transcript"),
                ],
                check=True,
                capture_output=True,
                timeout=240,
            )
            transcript = (root / "transcript.txt").read_text(encoding="utf-8").strip()
            if not transcript:
                raise ValueError("No speech was recognized; rerecord or type the answer")
            if len(transcript) > 6000:
                raise ValueError("Transcript exceeds 6000 characters; shorten the answer")
            if locale == "zh-Hant":
                from opencc import OpenCC

                transcript = OpenCC("s2twp").convert(transcript)
            return transcript, limited

    @staticmethod
    def backend(locale: str) -> str:
        return os.environ.get(
            "INTERVIEW_SIMULATOR_TTS_BACKEND_" + locale.replace("-", "_").upper(),
            os.environ.get("INTERVIEW_SIMULATOR_TTS_BACKEND", "auto"),
        )

    def speak(self, text: str, locale: str) -> bytes:
        if locale not in LANGUAGE or not 0 < len(text) <= 3000:
            raise ValueError("Unsupported language or utterance size")
        backend = self.backend(locale)
        if backend not in {"auto", "say", "piper", "windows", "open-jtalk"}:
            raise ValueError("Choose auto, say, piper, windows, or open-jtalk for local speech")
        if backend == "windows" or (backend == "auto" and windows_voice(locale)):
            voice_name = windows_voice(locale)
            if not voice_name:
                raise RuntimeError(f"Install a System.Speech voice for {locale}; run the local voice check")
            with tempfile.TemporaryDirectory(prefix="interview-voice-") as directory:
                wav = Path(directory) / "question.wav"
                windows_call({"action": "speak", "voice": voice_name, "output": str(wav), "text": text})
                return wav.read_bytes()
        if backend == "open-jtalk" or (backend == "auto" and locale == "ja" and jtalk_ready()):
            if locale != "ja":
                raise ValueError("Open JTalk is configured only for Japanese")
            with tempfile.TemporaryDirectory(prefix="interview-voice-") as directory:
                wav = Path(directory) / "question.wav"
                speak_jtalk(text, wav)
                return wav.read_bytes()
        voice = selected_voice(locale)
        piper_asset = asset_path(
            os.environ.get(f"INTERVIEW_SIMULATOR_PIPER_MODEL_{locale.replace('-', '_').upper()}")
        )
        piper_model = str(piper_asset) if piper_asset else None
        use_say = backend == "say" or (backend == "auto" and voice and shutil.which("say"))
        if not use_say:
            if (
                not piper_model
                or not Path(piper_model).is_file()
                or not Path(piper_model + ".json").is_file()
            ):
                raise RuntimeError(f"Configure a local Piper model and JSON voice file for {locale}")
            if not shutil.which("piper"):
                raise RuntimeError("Install the local Piper command before speech playback")
            with tempfile.TemporaryDirectory(prefix="interview-voice-") as directory:
                wav = Path(directory) / "question.wav"
                run_process(
                    ["piper", "--model", piper_model, "--output_file", str(wav)],
                    input=" ".join(text.splitlines()),
                    text=True,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                return wav.read_bytes()
        if not voice or not shutil.which("say") or not shutil.which("ffmpeg"):
            raise RuntimeError(f"Set a local macOS {locale} voice and install ffmpeg")
        with tempfile.TemporaryDirectory(prefix="interview-voice-") as directory:
            aiff = Path(directory) / "question.aiff"
            wav = Path(directory) / "question.wav"
            run_process(
                ["say", "-v", voice, "-o", str(aiff)],
                input=text,
                text=True,
                check=True,
                capture_output=True,
                timeout=45,
            )
            run_process(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(aiff),
                    "-ar",
                    "22050",
                    "-ac",
                    "1",
                    str(wav),
                ],
                check=True,
                capture_output=True,
                timeout=45,
            )
            return wav.read_bytes()
