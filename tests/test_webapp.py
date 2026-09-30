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
    run = {"answers": [object()] * 10, "evaluations": {1: {"score": 75}}}
    monkeypatch.setattr(webapp.engine.store, "get_run", lambda run_id: run)

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
