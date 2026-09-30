from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

LANGUAGE = {"en": "en", "ja": "ja", "zh-Hant": "zh"}


class Speech:
    """Local whole-turn recognition and speech. Requires user-installed native assets."""

    def __init__(self, model_path: Path | None = None):
        configured = os.environ.get("INTERVIEW_SIMULATOR_WHISPER_MODEL")
        self.model_path = model_path or (Path(configured) if configured else None)

    def capabilities(self) -> dict[str, object]:
        voices = {
            locale: os.environ.get(f"INTERVIEW_SIMULATOR_VOICE_{locale.replace('-', '_').upper()}")
            for locale in LANGUAGE
        }
        piper_models = {
            locale: os.environ.get(f"INTERVIEW_SIMULATOR_PIPER_MODEL_{locale.replace('-', '_').upper()}")
            for locale in LANGUAGE
        }
        status = {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "whisper_cli": bool(shutil.which("whisper-cli")),
            "whisper_model": bool(self.model_path and self.model_path.is_file()),
            "mac_say": bool(shutil.which("say")),
            "piper": bool(shutil.which("piper")),
            "configured_voices": voices,
            "configured_piper_models": piper_models,
        }
        status["asr_ready"] = bool(status["ffmpeg"] and status["whisper_cli"] and status["whisper_model"])
        status["mac_tts_ready"] = bool(status["ffmpeg"] and status["mac_say"] and all(voices.values()))
        status["piper_tts_ready"] = bool(
            status["piper"]
            and all(
                value and Path(value).is_file() and Path(value + ".json").is_file()
                for value in piper_models.values()
            )
        )
        backend = os.environ.get("INTERVIEW_SIMULATOR_TTS_BACKEND", "auto")
        by_language = {}
        for locale in LANGUAGE:
            mac_ready = bool(status["ffmpeg"] and status["mac_say"] and voices[locale])
            model = piper_models[locale]
            piper_ready = bool(
                status["piper"] and model and Path(model).is_file() and Path(model + ".json").is_file()
            )
            by_language[locale] = (
                mac_ready
                if backend == "say"
                else piper_ready
                if backend == "piper"
                else (mac_ready or piper_ready)
                if backend == "auto"
                else False
            )
        status["tts_backend"] = backend
        status["tts_by_language"] = by_language
        status["tts_ready"] = all(by_language.values())
        return status

    def transcribe(self, audio: bytes, locale: str) -> str:
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
            subprocess.run(
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
                    raise ValueError("Recording exceeds three minutes; shorten it or enter a typed answer")
            subprocess.run(
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
            return transcript

    def speak(self, text: str, locale: str) -> bytes:
        if locale not in LANGUAGE or not 0 < len(text) <= 3000:
            raise ValueError("Unsupported language or utterance size")
        backend = os.environ.get("INTERVIEW_SIMULATOR_TTS_BACKEND", "auto")
        if backend not in {"auto", "say", "piper"}:
            raise ValueError("TTS backend must be auto, say, or piper")
        voice = os.environ.get(f"INTERVIEW_SIMULATOR_VOICE_{locale.replace('-', '_').upper()}")
        piper_model = os.environ.get(f"INTERVIEW_SIMULATOR_PIPER_MODEL_{locale.replace('-', '_').upper()}")
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
                subprocess.run(
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
            subprocess.run(
                ["say", "-v", voice, "-o", str(aiff)],
                input=text,
                text=True,
                check=True,
                capture_output=True,
                timeout=45,
            )
            subprocess.run(
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
