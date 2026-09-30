from __future__ import annotations

from interview_simulator.speech import Speech


def test_piper_voice_works_without_macos_say(monkeypatch, tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    (tmp_path / "voice.onnx.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("INTERVIEW_SIMULATOR_TTS_BACKEND", "piper")
    monkeypatch.setenv("INTERVIEW_SIMULATOR_PIPER_MODEL_JA", str(model))
    monkeypatch.setattr(
        "interview_simulator.speech.shutil.which", lambda name: "/bin/piper" if name == "piper" else None
    )

    def fake_run(command, **kwargs):
        assert command[:3] == ["piper", "--model", str(model)]
        assert kwargs["input"] == "こんにちは"
        from pathlib import Path

        Path(command[-1]).write_bytes(b"RIFFsynthetic")

    monkeypatch.setattr("interview_simulator.speech.subprocess.run", fake_run)
    assert Speech().speak("こんにちは", "ja") == b"RIFFsynthetic"


def test_long_audio_is_rejected_instead_of_truncated(monkeypatch, tmp_path):
    import wave
    from pathlib import Path

    import pytest

    model = tmp_path / "model.bin"
    model.write_bytes(b"synthetic")
    monkeypatch.setattr("interview_simulator.speech.shutil.which", lambda _: "/bin/synthetic")

    def fake_run(command, **kwargs):
        assert command[0] == "ffmpeg"  # ASR must never run for a long recording.
        assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"
        assert "hls" not in command[command.index("-format_whitelist") + 1]
        with wave.open(str(Path(command[-1])), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(b"\x00\x00" * (181 * 16000))

    monkeypatch.setattr("interview_simulator.speech.subprocess.run", fake_run)
    with pytest.raises(ValueError, match="three minutes"):
        Speech(model).transcribe(b"synthetic", "en")


def test_say_receives_untrusted_text_on_stdin(monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("INTERVIEW_SIMULATOR_TTS_BACKEND", "say")
    monkeypatch.setenv("INTERVIEW_SIMULATOR_VOICE_EN", "Samantha")
    monkeypatch.setattr("interview_simulator.speech.shutil.which", lambda _: "/bin/synthetic")

    def fake_run(command, **kwargs):
        if command[0] == "say":
            assert "--output-file=/tmp/injected" not in command
            assert kwargs["input"] == "--output-file=/tmp/injected"
        else:
            Path(command[-1]).write_bytes(b"RIFFsynthetic")

    monkeypatch.setattr("interview_simulator.speech.subprocess.run", fake_run)
    assert Speech().speak("--output-file=/tmp/injected", "en") == b"RIFFsynthetic"
