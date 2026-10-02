from interview_simulator.config import Settings


def test_explicit_project_dotenv_and_shell_override(monkeypatch, tmp_path):
    (tmp_path / "InterviewWiki").mkdir()
    (tmp_path / "InterviewWiki/interviewwiki.yaml").write_text("version: 1\n")
    (tmp_path / ".env").write_text("INTERVIEW_SIMULATOR_GGUF=models/test.gguf\n")
    monkeypatch.delenv("INTERVIEW_SIMULATOR_GGUF", raising=False)
    assert Settings.load(tmp_path).model_path == tmp_path / "models/test.gguf"
    monkeypatch.setenv("INTERVIEW_SIMULATOR_GGUF", "models/override.gguf")
    assert Settings.load(tmp_path).model_path == tmp_path / "models/override.gguf"
