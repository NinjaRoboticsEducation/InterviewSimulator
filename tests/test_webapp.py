from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from interview_simulator import webapp
from interview_simulator.webapp import app


def test_local_browser_and_diagnostics_are_available():
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Interview-Token": webapp.REQUEST_TOKEN})
    page = client.get("/")
    assert page.status_code == 200
    assert "Start practice" in page.text
    assert "Adaptive question order" in page.text
    diagnostics = client.get("/api/doctor")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["model_endpoint"].startswith("http://127.0.0.1:")


def test_report_job_runs_in_background_and_exposes_result(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    run = {
        "answers": [{"skipped": False}] * 10,
        "evaluations": {1: {"score": 75}},
        "questions": [
            {"category": c}
            for c in ("personal", "professionalism", "portfolio", "role", "company")
            for _ in range(2)
        ],
        "locale": "en",
    }
    monkeypatch.setattr(webapp.engine.store, "get_run", lambda run_id: run)
    monkeypatch.setattr(webapp.engine.store, "lock_scoring", lambda *args: {})

    async def evaluate(run_id):
        await asyncio.sleep(0.02)
        report.write_text("# Report\n", encoding="utf-8")
        return report

    monkeypatch.setattr(webapp.engine, "evaluate", evaluate)
    webapp.report_tasks.clear()
    with TestClient(
        app, base_url="http://127.0.0.1", headers={"X-Interview-Token": webapp.REQUEST_TOKEN}
    ) as client:
        assert client.post("/api/runs/synthetic/report/start").status_code == 200
        for _ in range(20):
            result = client.get("/api/runs/synthetic/report/status").json()
            if result["status"] == "done":
                break
            import time

            time.sleep(0.01)
        assert result["status"] == "done"
        assert result["assessed"] == 1
        assert result["report"] == "# Report\n"
    webapp.report_tasks.clear()


def test_speech_readiness_does_not_require_model_fingerprinting(monkeypatch):
    monkeypatch.setattr(
        webapp.speech, "capabilities", lambda: {"asr_ready": False, "tts_by_language": {"en": True}}
    )
    monkeypatch.setattr(
        webapp, "diagnostics", lambda _: (_ for _ in ()).throw(AssertionError("must not hash LLM"))
    )
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Interview-Token": webapp.REQUEST_TOKEN})
    result = client.get("/api/speech")
    assert result.status_code == 200
    assert result.json()["tts_by_language"]["en"] is True
    assert client.get("/api/speech", headers={"X-Interview-Token": "wrong"}).status_code == 403


def test_report_error_never_returns_sdk_prompt_or_key(monkeypatch, tmp_path):
    from test_interview_flow import make_engine
    from test_refinement import answered

    engine = make_engine(tmp_path)
    run_id = answered(engine.store, engine.wiki.snapshot("example/engineer"))
    monkeypatch.setattr(webapp, "engine", engine)

    class FailedTask:
        def done(self):
            return True

        def cancelled(self):
            return False

        def exception(self):
            return RuntimeError("synthetic-secret-key and private fictional answer")

    monkeypatch.setitem(webapp.report_tasks, run_id, FailedTask())
    result = webapp.report_status(run_id)
    assert result["status"] == "failed"
    assert "synthetic-secret-key" not in str(result) and "private fictional answer" not in str(result)
