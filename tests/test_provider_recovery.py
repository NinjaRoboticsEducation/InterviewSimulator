from __future__ import annotations

import asyncio
import os
import signal
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_interview_flow import FakeWiki, make_engine

from interview_simulator import processes, webapp
from interview_simulator.model_checks import ModelChecks
from interview_simulator.portability import clear_history
from interview_simulator.providers import Binding, ProviderError, ProviderService
from interview_simulator.security import REQUEST_TOKEN, LocalRequestMiddleware


def test_model_validation_failure_is_json_and_content_free(monkeypatch):
    async def invalid(_binding):
        raise ValueError("FICTIONAL-SECRET and generated private output")

    monkeypatch.setattr(webapp.engine.providers, "probe", invalid)
    client = TestClient(webapp.app, base_url="http://127.0.0.1", headers={"X-Interview-Token": REQUEST_TOKEN})
    result = client.post("/api/providers/probe", json={"provider": "google", "model": "fictional"})
    assert result.status_code == 400
    assert result.json()["failure"]["code"] == "VALIDATION_FAILED"
    assert "FICTIONAL-SECRET" not in result.text


@pytest.mark.parametrize("code", ["RATE_LIMITED", "TEMPORARY_UNAVAILABLE", "TIMEOUT", "PROVIDER_UNAVAILABLE"])
def test_provider_outage_keeps_diagnostics_and_suggests_switching(code):
    error = ProviderError("Synthetic failure", code=code, http_status=503).diagnostic()
    assert error["recovery"] == "switch_provider"
    assert error["code"] == code and error["http_status"] == 503


def test_model_check_progress_replay_and_cancellation(tmp_path):
    async def exercise():
        ready = asyncio.Event()
        cancelled = asyncio.Event()

        async def probe(binding, progress):
            progress(3, 9)
            ready.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        service = SimpleNamespace(settings=SimpleNamespace(state_root=tmp_path), probe=probe)
        checks = ModelChecks()
        binding = Binding(provider="google", model="fictional")
        checks.start("a" * 32, binding, service)
        await ready.wait()
        assert checks.start("a" * 32, binding, service)["completed"] == 3
        with pytest.raises(ValueError):
            checks.start("b" * 32, binding, service)
        await checks.stop("a" * 32)
        assert cancelled.is_set() and checks.status("a" * 32)["status"] == "cancelled"
        await checks.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["pass", "fail", "idle", "timeout"])
def test_model_check_terminal_states_and_no_secret_leak(tmp_path, outcome):
    async def exercise():
        async def probe(binding, progress):
            if outcome == "pass":
                progress(1, 1)
                return {"passed": True}
            if outcome == "fail":
                raise ValueError("FICTIONAL-SECRET")
            await asyncio.Event().wait()

        service = SimpleNamespace(settings=SimpleNamespace(state_root=tmp_path), probe=probe)
        checks = ModelChecks(
            idle_seconds=0.02 if outcome == "idle" else 1,
            deadline_seconds=0.02 if outcome == "timeout" else 2,
        )
        checks.start("a" * 32, Binding(provider="google", model="fictional"), service)
        await checks.jobs["a" * 32]["task"]
        result = checks.status("a" * 32)
        assert result["status"] == ("passed" if outcome == "pass" else "failed")
        if outcome in {"idle", "timeout"}:
            assert result["failure"]["code"] == ("INTERRUPTED" if outcome == "idle" else "TIMEOUT")
        assert "FICTIONAL-SECRET" not in (tmp_path / "last-model-check.json").read_text()
        await checks.close()

    asyncio.run(exercise())


def test_browser_disconnect_cancels_request_work():
    async def exercise():
        started, cancelled = asyncio.Event(), asyncio.Event()
        count = 0

        async def receive():
            nonlocal count
            count += 1
            if count == 1:
                return {"type": "http.request", "body": b"", "more_body": False}
            await started.wait()
            return {"type": "http.disconnect"}

        async def send(_message):
            pass

        async def application(scope, receive, send):
            await receive()
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        middleware = LocalRequestMiddleware(application)
        await asyncio.wait_for(
            middleware(
                {
                    "type": "http",
                    "path": "/api/runs",
                    "scheme": "http",
                    "headers": [(b"host", b"127.0.0.1"), (b"x-interview-token", REQUEST_TOKEN.encode())],
                },
                receive,
                send,
            ),
            2,
        )
        assert cancelled.is_set()

    asyncio.run(exercise())


def test_native_cancellation_reaps_child_before_releasing_cpu_queue(monkeypatch, tmp_path):
    engine = make_engine(tmp_path)
    original = subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(processes.subprocess, "Popen", spawn)

    async def exercise():
        task = asyncio.create_task(
            engine.run_native(
                lambda: processes.run(
                    [sys.executable, "-c", "import time; time.sleep(60)"], timeout=240, capture_output=True
                )
            )
        )
        while not children:
            await asyncio.sleep(0.01)
        start = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - start < 5
        assert children[0].poll() is not None
        assert await engine.run_native(lambda: 123) == 123

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX targeted Ctrl+C; Windows subprocess contract tested separately"
)
def test_model_launcher_stops_child_when_only_wrapper_receives_ctrl_c(tmp_path):
    ready = tmp_path / "child-ready"
    child_code = f"import signal,time,pathlib; signal.signal(signal.SIGTERM, signal.SIG_IGN); pathlib.Path({str(ready)!r}).touch(); time.sleep(60)"
    wrapper = subprocess.Popen(
        [
            sys.executable,
            "-c",
            'from interview_simulator.processes import serve_native; import sys; serve_native([sys.executable,"-c",sys.argv[1]])',
            child_code,
        ],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        wrapper.send_signal(signal.SIGINT)
        assert wrapper.wait(timeout=6) == 0
    finally:
        # Test owns this isolated process group, including any child after a failed assertion.
        try:
            os.killpg(wrapper.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        wrapper.wait(timeout=3)


def test_clear_history_removes_runs_and_caches_preserves_profile_and_settings(monkeypatch, tmp_path):
    monkeypatch.setattr("interview_simulator.portability.WikiAdapter", lambda path: FakeWiki(path.parent))
    engine = make_engine(tmp_path)
    asyncio.run(engine.start("example/engineer", "en"))
    state = engine.settings.state_root
    protected = tmp_path / "InterviewWiki/PersonalWiki/raw/resume.txt"
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text("FICTIONAL_PROFILE")
    settings = state / "model-settings.json"
    settings.write_text("FICTIONAL_SETTINGS")
    cache = state / "translation-cache/q.json"
    cache.parent.mkdir()
    cache.write_text("FICTIONAL_HISTORY")
    backup = state / "question-bank.pre-v3.sqlite"
    backup.write_bytes(b"FICTIONAL_HISTORY")
    result = clear_history(engine.settings)
    assert result["runs_removed"] == 1
    assert engine.store.list_runs() == [] and not cache.exists() and not backup.exists()
    assert protected.read_text() == "FICTIONAL_PROFILE" and settings.read_text() == "FICTIONAL_SETTINGS"
    with sqlite3.connect(state / "adk-sessions.sqlite") as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    assert clear_history(engine.settings)["runs_removed"] == 0


def test_clear_history_obeys_server_lease(monkeypatch, tmp_path):
    from filelock import FileLock, Timeout

    monkeypatch.setattr("interview_simulator.portability.WikiAdapter", lambda path: FakeWiki(path.parent))
    engine = make_engine(tmp_path)
    with FileLock(engine.settings.state_root / "server.lock"), pytest.raises(Timeout):
        clear_history(engine.settings)


def test_clear_history_rejects_link_before_deleting_run(monkeypatch, tmp_path):
    monkeypatch.setattr("interview_simulator.portability.WikiAdapter", lambda path: FakeWiki(path.parent))
    engine = make_engine(tmp_path)
    state = asyncio.run(engine.start("example/engineer", "en"))
    external = tmp_path / "keep.txt"
    external.write_text("keep")
    link = engine.wiki.simulation_dir("example/engineer", state["run_id"]) / "linked.txt"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("Symbolic links unavailable")
    with pytest.raises(ValueError, match="Symbolic links"):
        clear_history(engine.settings)
    assert engine.store.get_run(state["run_id"]) and external.read_text() == "keep"


def test_preparation_cancel_settles_worker_and_saved_run(tmp_path, monkeypatch):
    async def exercise():
        engine = make_engine(tmp_path)
        engine.providers = ProviderService(engine.settings)
        monkeypatch.setattr(webapp, "engine", engine)
        monkeypatch.setattr(webapp, "preparation_tasks", {})
        original_start = engine.start
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def blocked(*args):
            await original_start(*args)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(engine, "start", blocked)
        request = webapp.StartRequest(opportunity="example/engineer", request_id="b" * 32)
        pending = asyncio.create_task(webapp.start(request))
        await asyncio.wait_for(started.wait(), 5)
        result = await webapp.cancel_preparation(request.request_id)
        response = await pending
        assert result == {"cancelled": True} and response.status_code == 409
        assert cancelled.is_set() and not webapp.preparation_tasks
        run_id = engine.store.request_run(request.request_id)
        assert engine.store.get_run(run_id)["status"] == "cancelled"

    asyncio.run(exercise())
