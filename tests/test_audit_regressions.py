from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_interview_flow import make_engine

from interview_simulator import webapp
from interview_simulator.adk_runtime import LocalAdk
from interview_simulator.config import Settings
from interview_simulator.files import private_database
from interview_simulator.report import _safe
from interview_simulator.security import REQUEST_TOKEN, LocalRequestMiddleware


def test_browser_boundary_and_limits():
    client = TestClient(webapp.app, base_url="http://127.0.0.1")
    assert client.get("/api/active").status_code == 403
    headers = {"X-Interview-Token": REQUEST_TOKEN}
    assert client.get("/api/active", headers=headers).status_code == 200
    assert client.get("/api/active", headers={**headers, "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/runs", headers=headers, content=b"x" * 100001).status_code == 413
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200


def test_chunked_body_rejected_before_downstream_parser():
    async def exercise():
        called = False

        async def downstream(scope, receive, send):
            nonlocal called
            called = True

        chunks = iter([b"x" * 60000, b"y" * 60000])

        async def receive():
            return {"type": "http.request", "body": next(chunks), "more_body": True}

        sent = []

        async def send(message):
            sent.append(message)

        await LocalRequestMiddleware(downstream)(
            {
                "type": "http",
                "scheme": "http",
                "path": "/api/runs",
                "headers": [(b"host", b"127.0.0.1"), (b"x-interview-token", REQUEST_TOKEN.encode())],
            },
            receive,
            send,
        )
        assert not called
        assert sent[0]["status"] == 413

    asyncio.run(exercise())


def test_symlink_database_rejected_and_permissions_private(tmp_path):
    target = tmp_path / "target"
    target.write_text("untouched")
    link = tmp_path / "alias.sqlite"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="Symbolic"):
        private_database(link)
    assert target.read_text() == "untouched"
    database = tmp_path / "private" / "bank.sqlite"
    private_database(database)
    if os.name != "nt":
        assert database.stat().st_mode & 0o777 == 0o600
        assert database.parent.stat().st_mode & 0o777 == 0o700


def test_concurrent_recovery_only_resumes_once(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        state = await engine.start("example/engineer", "en")
        run_id = state["run_id"]
        engine.store.acknowledge_presentation(run_id, 1, state["question"]["event_id"])
        engine.store.submit(run_id, 1, "saved", "Answer")
        states = await asyncio.gather(*(engine.state(run_id) for _ in range(4)))
        assert {item["question"]["ordinal"] for item in states} == {2}
        assert len(engine.store.get_run(run_id)["answers"]) == 1
        with pytest.raises(ValueError, match="Resume"):
            await engine.start("example/engineer", "en")

    asyncio.run(exercise())


def test_score_survives_cancelled_coaching_and_report_revisions(tmp_path):
    class Assessor:
        calls = 0
        cancel = True

        async def evaluate(self, *args):
            self.calls += 1
            return {
                "score": 75,
                "scores": {k: 3 for k in ("relevance", "specificity", "reasoning", "clarity", "reflection")},
                "quote": "Answer",
                "strength": "Clear",
                "improvement": "Give results",
                "reason": "Relevant",
                "fact_ids": [],
            }

        async def coach(self, *args):
            if self.cancel:
                raise asyncio.CancelledError()
            return {
                "example": "Verified work",
                "why_it_works": "Relevant",
                "outline": "Result",
                "next_action": "Practice",
                "fact_ids": [],
            }

    async def exercise():
        engine = make_engine(tmp_path)
        engine.adk = Assessor()
        state = await engine.start("example/engineer", "en")
        run_id = state["run_id"]
        for ordinal in range(1, 11):
            engine.store.acknowledge_presentation(run_id, ordinal, state["question"]["event_id"])
            state = await engine.submit(run_id, ordinal, "Answer", str(ordinal))
        with pytest.raises(asyncio.CancelledError):
            await engine.evaluate(run_id)
        assert engine.store.get_run(run_id)["evaluations"][1]["score"] == 75
        engine.adk.cancel = False
        report = await engine.evaluate(run_id)
        assert engine.adk.calls == 10
        assert await engine.evaluate(run_id) == report
        revision = report.with_name("report-r12.md")
        revision.write_text("older content")
        assert engine.latest_report(run_id) == report  # an orphan is never a committed export
        assert await engine.evaluate(run_id) == report
        assert revision.read_text() == "older content"
        report.with_name("report-r99.md").symlink_to(report)
        with pytest.raises(ValueError, match="Symbolic"):
            engine.latest_report(run_id)

    asyncio.run(exercise())


def test_local_adk_uses_isolated_http_transport(monkeypatch, tmp_path):
    import litellm  # noqa: F401 - initialize dependency before intercepting our transport

    original = httpx.AsyncClient
    requests = []

    def reply(request):
        requests.append(request)
        if request.url.path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 4096}})
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "Rendered synthetic template"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1] * 30})
        assert str(request.url) == "http://127.0.0.1:8081/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "local",
                "object": "chat.completion",
                "created": 0,
                "model": "interview-local",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"ok":true}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    class client(original):
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False
            super().__init__(**kwargs, transport=httpx.MockTransport(reply))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    adapter = LocalAdk(Settings(tmp_path, tmp_path, tmp_path / "state"))
    assert '"ok"' in asyncio.run(adapter._run_agent("test_assessor", "Return JSON", {"answer": "synthetic"}))
    assert len(requests) == 4


def test_report_escapes_active_content():
    rendered = _safe("![image](https://evil.example/pixel)<script>alert(1)</script>")
    assert "![image](" not in rendered
    assert "<script>" not in rendered


@pytest.mark.parametrize(
    "url", ["http://localhost:8081/v1", "https://example.com/v1", "http://127.0.0.1:8081/v1?redirect=x"]
)
def test_direct_settings_cannot_bypass_loopback(url):
    with pytest.raises(ValueError):
        Settings(Path("."), Path("."), Path("."), model_url=url)


def test_run_snapshot_rejects_tampering_and_repairs_missing_file(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        state = await engine.start("example/engineer", "en")
        run_id = state["run_id"]
        snapshot = tmp_path / "Simulations" / run_id / "input-snapshot.json"
        snapshot.unlink()
        await engine.state(run_id)
        assert snapshot.is_file()
        snapshot.write_text("{}")
        with pytest.raises(ValueError, match="snapshot was changed"):
            await engine.state(run_id)

    asyncio.run(exercise())


def test_server_lease_rejects_second_process(monkeypatch, tmp_path):
    from filelock import FileLock, Timeout

    engine = make_engine(tmp_path)
    monkeypatch.setattr(webapp, "engine", engine)
    with (
        FileLock(engine.settings.state_root / "server.lock", timeout=0),
        pytest.raises(Timeout),
        TestClient(webapp.app, base_url="http://127.0.0.1"),
    ):
        pass
