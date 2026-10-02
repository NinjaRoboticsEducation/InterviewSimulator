"""Optional operating-system adapters. Speech text is data on stdin, never executable code."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from .processes import run as run_process

WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($request.action -eq 'list') {
        $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object {
            @{ name = $_.VoiceInfo.Name; culture = $_.VoiceInfo.Culture.Name }
        })
        ConvertTo-Json -InputObject $voices -Compress
    } elseif ($request.action -eq 'speak') {
        $synth.SelectVoice($request.voice)
        $synth.SetOutputToWaveFile($request.output)
        $synth.Speak($request.text)
        $synth.SetOutputToNull()
    } else { throw 'Invalid speech action' }
} finally { $synth.Dispose() }
"""


def windows_call(payload: dict) -> str:
    if platform.system() != "Windows" or not shutil.which("powershell.exe"):
        raise RuntimeError(
            "Windows local speech requires Windows PowerShell and installed System.Speech voices"
        )
    result = run_process(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_SCRIPT],
        input=json.dumps(payload, ensure_ascii=True),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=60,
    )
    return result.stdout


@lru_cache(maxsize=1)
def windows_voices() -> dict[str, str]:
    if platform.system() != "Windows":
        return {}
    try:
        values = json.loads(windows_call({"action": "list"}))
        return {
            v["name"]: v["culture"]
            for v in values
            if isinstance(v, dict) and isinstance(v.get("name"), str) and isinstance(v.get("culture"), str)
        }
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError):
        return {}


def windows_voice(locale: str) -> str | None:
    voices = windows_voices()
    configured = os.environ.get("INTERVIEW_SIMULATOR_WINDOWS_VOICE_" + locale.replace("-", "_").upper())
    if configured:
        return configured if configured in voices else None
    cultures = {"en": ("en-US", "en-GB"), "ja": ("ja-JP",), "zh-Hant": ("zh-TW", "zh-CN")}[locale]
    return next((name for culture in cultures for name, tag in voices.items() if tag == culture), None)


def asset_path(value: str | None) -> Path | None:
    return Path(__file__).resolve().parents[2] / Path(value).expanduser() if value else None


def jtalk_assets() -> tuple[Path | None, Path | None]:
    return (
        asset_path(os.environ.get("INTERVIEW_SIMULATOR_OPENJTALK_DICTIONARY")),
        asset_path(os.environ.get("INTERVIEW_SIMULATOR_OPENJTALK_VOICE")),
    )


def jtalk_ready() -> bool:
    dictionary, voice = jtalk_assets()
    return bool(
        shutil.which("open_jtalk") and dictionary and dictionary.is_dir() and voice and voice.is_file()
    )


def speak_jtalk(text: str, wav: Path) -> None:
    if not jtalk_ready():
        raise RuntimeError("Configure open_jtalk, its UTF-8 dictionary, and an HTS Japanese voice")
    dictionary, voice = jtalk_assets()
    run_process(
        ["open_jtalk", "-x", str(dictionary), "-m", str(voice), "-ow", str(wav)],
        input=text,
        text=True,
        encoding="utf-8",
        check=True,
        capture_output=True,
        timeout=60,
    )
