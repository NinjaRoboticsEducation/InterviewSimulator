from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_interview_flow import FakeWiki, make_engine

from interview_simulator.adk_runtime import EVALUATION_SCHEMA, LocalAdk
from interview_simulator.config import Settings
from interview_simulator.evaluation import validate_coaching
from interview_simulator.providers import Binding, ModelPlan, ProviderError, ProviderService
from interview_simulator.providers.adk_model import CloudTextLlm
from interview_simulator.providers.credentials import Credentials
from interview_simulator.questions import compose_variants, make_fixed_questions
from interview_simulator.report_view import safe_markdown, statistics
from interview_simulator.storage import Store

SECRET = "synthetic-secret-not-a-real-key"


def settings(root):
    return Settings(root, root / "InterviewWiki", root / ".simulator")


def answered(store, snapshot):
    run_id = store.create_run("example/engineer", "en", snapshot, make_fixed_questions(snapshot, "en"))
    for ordinal in range(1, 11):
        q = store.present(run_id, ordinal)
        store.acknowledge_presentation(run_id, ordinal, q["event_id"])
        store.submit(run_id, ordinal, f"a-{ordinal}", f"Answer {ordinal}", expected_revision=ordinal - 1)
    return run_id


def test_answer_versions_conflicts_lock_and_reopen(tmp_path):
    snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
    store = Store(tmp_path / "bank.sqlite")
    run_id = answered(store, snapshot)
    original_questions = store.get_run(run_id)["questions"]
    store.edit(run_id, 1, "Revised verified answer", "edit-1", 10)
    store.edit(run_id, 1, "Revised verified answer", "edit-1", 10)  # retry is idempotent
    assert store.get_run(run_id)["revision"] == 11
    with pytest.raises(ValueError, match="another tab"):
        store.edit(run_id, 2, "Stale answer", "edit-2", 10)
    frozen = store.lock_scoring(run_id, 11)
    assert frozen["answers"][0]["text"] == "Revised verified answer"
    with pytest.raises(ValueError, match="locked"):
        store.edit(run_id, 1, "Too late", "edit-late", 12)
    reopened = Store(store.path)
    assert reopened.lock_scoring(run_id) == frozen
    assert reopened.get_run(run_id)["questions"] == original_questions
    with reopened.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM answer_versions").fetchone()[0] == 2
        assert (
            json.loads(db.execute("SELECT payload_json FROM answer_versions WHERE version=1").fetchone()[0])[
                "text"
            ]
            == "Answer 1"
        )


def test_migration_is_backed_up_and_serialized(tmp_path):
    path = tmp_path / "bank.sqlite"
    store = Store(path)
    snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
    run_id = answered(store, snapshot)
    with sqlite3.connect(path) as db:
        for column in ("revision", "scoring_json", "report_state", "summary_json"):
            db.execute(f"ALTER TABLE runs DROP COLUMN {column}")
        db.execute("PRAGMA user_version=1")
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: Store(path), range(2)))
    with sqlite3.connect(tmp_path / "bank.pre-v2.sqlite") as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert "revision" not in {r[1] for r in backup.execute("PRAGMA table_info(runs)")}
    assert Store(path).get_run(run_id)["revision"] == 0


def test_pause_review_edit_do_not_advance_adk(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        state = await engine.start("example/engineer", "en", flow_mode="adaptive")
        engine.store.acknowledge_presentation(state["run_id"], 1, state["question"]["event_id"])
        state = await engine.submit(state["run_id"], 1, "Initial answer", "one", expected_revision=0)
        second = state["question"]
        before = engine.store.get_run(state["run_id"])["selection_decisions"]
        await engine.edit(state["run_id"], 1, "Revised answer", "edit", state["revision"])
        assert engine.review(state["run_id"])["answers"][0]["text"] == "Revised answer"
        assert engine.store.get_run(state["run_id"])["selection_decisions"] == before
        paused = await engine.action(state["run_id"], "pause", state["revision"] + 1)
        assert paused["question"] is None
        resumed = await engine.action(state["run_id"], "resume", paused["revision"])
        assert resumed["question"] == second
        cancelled = await engine.action(state["run_id"], "cancel", resumed["revision"])
        assert cancelled["status"] == "cancelled"
        assert engine.store.active_run() is None

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "provider,model",
    [("openai", "gpt-6.1-sol"), ("google", "gemini-3.8-flash"), ("anthropic", "claude-sonnet-5-5")],
)
def test_provider_wire_contracts_and_secret_exclusion(tmp_path, provider, model):
    requests = []

    def handler(request):
        requests.append(request)
        assert (
            request.url.host
            == {
                "openai": "api.openai.com",
                "google": "generativelanguage.googleapis.com",
                "anthropic": "api.anthropic.com",
            }[provider]
        )
        body = json.loads(request.content)
        assert "chat_template_kwargs" not in str(body)
        assert "api_key" not in body
        if provider == "openai":
            assert body["store"] is False and body["text"]["format"]["strict"] is True
            return httpx.Response(
                200,
                json={
                    "model": model,
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )
        if provider == "google":
            assert body["generationConfig"]["responseMimeType"] == "application/json"
            return httpx.Response(
                200,
                json={
                    "modelVersion": model,
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [{"text": "hidden", "thought": True}, {"text": '{"ok":true}'}]
                            },
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
                },
            )
        assert "minimum" not in str(body["output_config"]["format"]["schema"])
        return httpx.Response(
            200,
            json={
                "model": model,
                "stop_reason": "end_turn",
                "content": [
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": '{"ok":true}'},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    service = ProviderService(settings(tmp_path), httpx.MockTransport(handler))
    service.credentials.set(provider, SECRET)
    binding = Binding(provider=provider, model=model)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    adapter = CloudTextLlm(service, binding, "Instruction", schema)
    assert SECRET not in adapter.model_dump_json() + repr(adapter) + repr(service.credentials)
    result = asyncio.run(service.generate(binding, "Instruction", "Synthetic prompt", schema))
    assert json.loads(result) == {"ok": True}
    assert service.last_call["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert SECRET not in json.dumps(service.last_call)
    assert requests[0].url.scheme == "https"
    assert SECRET not in "".join(p.read_text() for p in settings(tmp_path).state_root.glob("*.json"))


def test_provider_errors_never_echo_keys_or_retry_timeouts(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(SECRET, request=request)

    service = ProviderService(settings(tmp_path), httpx.MockTransport(handler))
    service.credentials.set("openai", SECRET)
    with pytest.raises(ProviderError, match="may have been billed") as caught:
        asyncio.run(service.generate(Binding(provider="openai", model="gpt-6.1-sol"), "test", "test", {}))
    assert SECRET not in str(caught.value)
    assert len(calls) == 1


def test_discovery_pagination_unknown_models_and_malformed_caps(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "gpt-6.1-sol", "capabilities": {"structured_outputs": None}},
                        {"id": "future-model", "display_name": {}},
                        {"id": None},
                    ],
                    "has_more": True,
                    "last_id": "cursor-1",
                },
            )
        assert request.url.params["after_id"] == "cursor-1"
        return httpx.Response(200, json={"data": [{"id": "future-model"}, {"id": "bad?query"}]})

    service = ProviderService(settings(tmp_path), httpx.MockTransport(handler))
    service.credentials.set("openai", SECRET)
    result = asyncio.run(service.discover("openai"))
    assert len(result) == 2
    assert result[0]["compatible"] is True
    assert result[1]["compatible"] is False
    assert result[1]["name"] == "future-model"


def test_actual_adk_cloud_workflow_and_call_budget(tmp_path):
    raw = {
        "scores": dict.fromkeys(("relevance", "specificity", "reasoning", "clarity", "reflection"), 3),
        "quote": "I built it",
        "strength": "Specific ownership",
        "improvement": "Explain your result",
        "reason": "A clear approach",
        "fact_ids": ["fact-abc"],
    }

    def handler(request):
        assert request.url.path == "/v1/responses"
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(raw)}]}
                ],
            },
        )

    cfg = settings(tmp_path)
    service = ProviderService(cfg, httpx.MockTransport(handler))
    service.credentials.set("openai", SECRET)
    plan = ModelPlan(evaluation=Binding(provider="openai", model="gpt-6.1-sol"), max_calls=1)
    adk = LocalAdk(cfg, service, plan)
    adk.store = Store(cfg.state_root / "bank.sqlite")
    snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
    adk.run_id = answered(adk.store, snapshot)
    question = {"text": "What did you build?", "locale": "en", "category": "portfolio", "ordinal": 1}
    result = asyncio.run(
        adk.evaluate(question, "I built it", {"fact-abc": "Built a test service."}, "Python")
    )
    assert result["score"] == 75
    assert result["provenance"]["provider"] == "openai"
    with adk.store.connect() as db:
        attempt = db.execute("SELECT * FROM model_attempts").fetchone()
        assert attempt["status"] == "succeeded" and attempt["ordinal"] == 1
    with pytest.raises(ProviderError, match="budget"):
        asyncio.run(adk._run_agent("answer_assessor", "test", {}, EVALUATION_SCHEMA))
    assert SECRET.encode() not in (cfg.state_root / "adk-sessions.sqlite").read_bytes()


def test_html_and_score_calculations_reject_untrusted_content():
    markup = safe_markdown(
        '# Hello\n<script>alert(1)</script>\n[click](javascript:alert(1))\n<img src="https://evil.example/track" onerror="x">\n[relative](/api/settings)\n| Name | Score |\n| --- | --- |\n| Clarity | 75 |'
    )
    assert "<script" not in markup and 'href="javascript:' not in markup and "<img" not in markup
    assert 'href="/api' not in markup and "<table>" in markup
    run = {
        "evaluations": {
            1: {"score": 75, "scores": {"clarity": 3}},
            2: {"score": float("nan")},
            3: {"score": True},
        },
        "questions": [{"category": "personal"}] * 10,
        "answers": [{"skipped": False}] * 10,
    }
    stats = statistics(run)
    assert stats["overall"] == 75 and stats["assessed"] == 1 and not stats["complete"]
    assert stats["dimensions"][3]["score"] == 75


def test_coaching_evidence_slots_cannot_invent_results():
    raw = {
        "fact_ids": ["f1"],
        "why_it_works": "Connect the action to the requirement.",
        "outline": "Explain testing decisions.",
        "next_action": "Practise an example of the rollback decision.",
        "example_parts": [{"slot": "action", "fact_id": "f1"}],
    }
    result = validate_coaching(
        raw, {"f1": "Built a test service."}, {"locale": "en", "category": "portfolio"}
    )
    assert "Built a test service." in result["example"]
    assert "[add" not in result["example"]
    assert result["outline"] == raw["outline"]
    with pytest.raises(ValueError, match="approved fact"):
        validate_coaching(
            {**raw, "example_parts": [{"slot": "result", "fact_id": "made-up"}]},
            {"f1": "Built a test service."},
            {"locale": "en", "category": "portfolio"},
        )


def test_question_variants_preserve_intro_coverage_and_evidence(tmp_path):
    snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
    deck = make_fixed_questions(snapshot, "ja")
    choices = [
        {"ordinal": i, "focus": "baseline" if i == 1 else "reflection", "fact_id": ""} for i in range(1, 11)
    ]
    variants = compose_variants(deck, choices, {"fact-abc": "Built a test service."})
    assert variants[0] == deck[0] and [q.category for q in variants] == [q.category for q in deck]
    assert "改善" in variants[-1].text
    with pytest.raises(ValueError, match="unsupported evidence"):
        compose_variants(
            deck, [{**c, "fact_id": "unknown"} for c in choices], {"fact-abc": "Built a test service."}
        )


def test_key_validation_response_never_echoes_input():
    from interview_simulator import webapp

    client = TestClient(
        webapp.app, base_url="http://127.0.0.1", headers={"X-Interview-Token": webapp.REQUEST_TOKEN}
    )
    response = client.post("/api/providers/openai/connect", json={"key": {"secret": SECRET}})
    assert response.status_code == 422 and SECRET not in response.text


def test_no_plaintext_vault_fallback_and_copied_metadata(tmp_path, monkeypatch):
    creds = Credentials(tmp_path / "original")
    monkeypatch.setattr(creds, "_vault", lambda: (_ for _ in ()).throw(ProviderError("Unavailable")))
    with pytest.raises(ProviderError, match="session-only"):
        creds.set("openai", SECRET, remember=True)
    assert creds.status()["openai"]["connected"] is False
    destination = tmp_path / "copy"
    destination.mkdir()
    (destination / "credential-profiles.json").write_bytes(creds.path.read_bytes())
    copied = Credentials(destination)
    assert copied.metadata["installation"] != creds.metadata["installation"]
    with pytest.raises(ProviderError):
        copied.get("openai")


def test_installer_dry_run_and_redirect_restrictions(capsys):
    path = Path(__file__).resolve().parents[1] / "scripts/setup_environment.py"
    spec = importlib.util.spec_from_file_location("installer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--profile", "cloud-text", "--dry-run"]) == 0
    assert "no files" in capsys.readouterr().out
    assert module.permitted_url("https://huggingface.co/test")
    assert not module.permitted_url("http://huggingface.co/test")
    assert not module.permitted_url("https://huggingface.co.evil.example/test")
    assert not module.permitted_url("https://key@huggingface.co/test")


def test_generated_deck_summary_and_exports_through_real_adk(tmp_path):
    from interview_simulator.report_view import report_html

    calls = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "gpt-6.1-sol"}]})
        body = json.loads(request.content)
        calls.append(body)
        instruction = body["instructions"]
        payload = json.loads(body["input"])
        if "Design a natural" in instruction:
            raw = {"questions": [{"ordinal": i, "focus": "baseline", "fact_id": ""} for i in range(1, 11)]}
        elif "fair interview assessor" in instruction:
            raw = {
                "scores": dict.fromkeys(
                    ("relevance", "specificity", "reasoning", "clarity", "reflection"), 3
                ),
                "quote_span_id": next(iter(payload["answer_spans"])),
                "strength": "A clear action.",
                "improvement": "Explain a verified result.",
                "reason": "Relevant ownership.",
                "fact_ids": ["fact-abc"],
            }
        elif "practical career coach" in instruction:
            raw = {
                "fact_ids": ["fact-abc"],
                "example_clauses": [
                    {"text": "I built a test service.", "kind": "fact", "fact_ids": ["fact-abc"]}
                ],
                "why_it_works": "Uses confirmed actions.",
                "outline": "Explain context and action.",
                "next_action": "Verify an outcome before including it.",
            }
        elif "Audit the proposed" in instruction:
            raw = {"supported": True, "reason": "OK", "clause_indices": []}
        else:
            raw = {"priorities": [1, 7, 9]}
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(raw)}]}
                ],
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        )

    async def exercise():
        engine = make_engine(tmp_path)
        service = ProviderService(engine.settings, httpx.MockTransport(handler))
        service.credentials.set("openai", SECRET)
        cloud = Binding(provider="openai", model="gpt-6.1-sol")
        service.plan = ModelPlan(
            questions=cloud,
            evaluation=cloud,
            coaching=cloud,
            summary=cloud,
            generate_questions=True,
            generate_summary=True,
        )
        engine.providers = service
        engine.adk = LocalAdk(engine.settings, service)
        with pytest.raises(ValueError, match="Confirm cloud"):
            await engine.start("example/engineer", "en")
        state = await engine.start("example/engineer", "en", cloud_consent=True)
        run_id = state["run_id"]
        for ordinal in range(1, 11):
            engine.store.acknowledge_presentation(run_id, ordinal, state["question"]["event_id"])
            state = await engine.submit(
                run_id,
                ordinal,
                f"I built it: answer {ordinal}",
                f"answer-{ordinal}",
                expected_revision=state["revision"],
            )
        path = await engine.evaluate(run_id)
        run = engine.store.get_run(run_id)
        assert run["report_state"] == "complete"
        assert run["summary_result"]["priorities"] == [1, 7, 9]
        assert run["snapshot"]["question_design"]["provider"] == "openai"
        assert run["snapshot"]["cloud_text_consent"]["approved"] is True
        assert len(calls) == 32
        assert "Topic scores" in report_html(path.read_text(), run)
        exported = json.loads((path.parent / "run-export-report.json").read_text())
        assert exported["report_state"] == "complete"
        assert SECRET not in json.dumps(exported)
        assert SECRET.encode() not in (engine.settings.state_root / "adk-sessions.sqlite").read_bytes()
        with engine.store.connect() as db:
            assert (
                db.execute('SELECT COUNT(*) FROM model_attempts WHERE status="succeeded"').fetchone()[0] == 32
            )
        before = len(calls)
        await engine.evaluate(run_id)
        assert len(calls) == before  # report retry cannot rescore or rebill completed work

    asyncio.run(exercise())


def test_cjk_match_terms_preserve_partial_topic_overlap():
    from interview_simulator.selection import tokens

    assert "改善" in tokens("流程改善與測試") & tokens("如何改善測試流程？")
    assert "テス" in tokens("テストを改善しました") & tokens("テストの進め方は？")
    assert "python" in tokens("Ｐｙｔｈｏｎ testing")


def test_windows_speech_passes_text_as_data_on_stdin(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from interview_simulator import local_voices

    monkeypatch.setattr(local_voices.platform, "system", lambda: "Windows")
    monkeypatch.setattr(local_voices.shutil, "which", lambda name: "/synthetic/powershell.exe")
    text = "$(Remove-Item 'anything'); 日本語"

    def run(command, **kwargs):
        assert text not in command[-1]
        payload = json.loads(kwargs["input"])
        assert payload["text"] == text
        assert kwargs["encoding"] == "utf-8" and kwargs["timeout"] == 60
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(local_voices.subprocess, "run", run)
    local_voices.windows_call(
        {"action": "speak", "text": text, "output": str(tmp_path / "q.wav"), "voice": "Synthetic"}
    )


def test_open_jtalk_keeps_text_off_command_line(monkeypatch, tmp_path):
    from interview_simulator import local_voices

    voice = tmp_path / "Japanese.htsvoice"
    voice.write_bytes(b"synthetic")
    monkeypatch.setenv("INTERVIEW_SIMULATOR_OPENJTALK_DICTIONARY", str(tmp_path))
    monkeypatch.setenv("INTERVIEW_SIMULATOR_OPENJTALK_VOICE", str(voice))
    monkeypatch.setattr(local_voices.shutil, "which", lambda _: "/synthetic/open_jtalk")

    def run(command, **kwargs):
        assert command == [
            "open_jtalk",
            "-x",
            str(tmp_path),
            "-m",
            str(voice),
            "-ow",
            str(tmp_path / "q.wav"),
        ]
        assert kwargs["input"] == "こんにちは" and kwargs["encoding"] == "utf-8"

    monkeypatch.setattr(local_voices.subprocess, "run", run)
    local_voices.speak_jtalk("こんにちは", tmp_path / "q.wav")


def test_local_context_budget_rejects_oversized_input_without_generation(tmp_path):
    from interview_simulator.adk_runtime import InputBudgetError

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 4096}})
        if request.url.path == "/apply-template":
            return httpx.Response(404)
        assert request.url.path == "/tokenize"
        return httpx.Response(200, json={"tokens": [1] * 3500})

    async def exercise():
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(InputBudgetError, match="context budget"):
                await LocalAdk(settings(tmp_path))._local_budget(client, "Instructions", "Long answer", 1024)

    asyncio.run(exercise())
    assert calls == ["/props", "/apply-template", "/tokenize"]


def test_installer_recovers_fully_downloaded_partial_without_network(tmp_path, monkeypatch):
    import hashlib

    path = Path(__file__).resolve().parents[1] / "scripts/setup_environment.py"
    spec = importlib.util.spec_from_file_location("installer_partial", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    content = b"synthetic verified model"
    (tmp_path / "model.gguf.partial").write_bytes(content)
    asset = {
        "path": "model.gguf",
        "url": "https://huggingface.co/synthetic",
        "maximum_bytes": 1000,
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    monkeypatch.setattr(
        module, "build_opener", lambda *args: (_ for _ in ()).throw(AssertionError("No network needed"))
    )
    result = module.download(tmp_path, asset)
    assert result.read_bytes() == content and not (tmp_path / "model.gguf.partial").exists()


def test_provider_rejects_accidental_secret_echo(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": SECRET,
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps({"leaked": SECRET})}],
                    }
                ],
            },
        )

    service = ProviderService(settings(tmp_path), httpx.MockTransport(handler))
    service.credentials.set("openai", SECRET)
    with pytest.raises(ProviderError, match="unsafe output") as caught:
        asyncio.run(service.generate(Binding(provider="openai", model="gpt-6.1-sol"), "test", "test", {}))
    assert SECRET not in str(caught.value) and not service.last_call


def test_stopping_idle_or_finished_report_preserves_editability(monkeypatch, tmp_path):
    from interview_simulator import webapp

    engine = make_engine(tmp_path)
    state = asyncio.run(engine.start("example/engineer", "en"))
    monkeypatch.setattr(webapp, "engine", engine)
    webapp.report_tasks.clear()
    client = TestClient(
        webapp.app,
        base_url="http://127.0.0.1",
        headers={"X-Interview-Token": webapp.REQUEST_TOKEN},
    )
    result = client.post(f"/api/runs/{state['run_id']}/report/stop")
    assert result.status_code == 200
    assert result.json()["stopped"] is False
    stored = engine.store.get_run(state["run_id"])
    assert stored["report_state"] == "idle"
    assert not stored["scoring_json"]
    assert asyncio.run(engine.state(state["run_id"]))["editable"] is True
    assert client.post("/api/runs/missing/report/stop").status_code == 404


def test_stopping_active_report_awaits_worker_before_retry(monkeypatch, tmp_path):
    from interview_simulator import webapp

    engine = make_engine(tmp_path)
    run_id = answered(engine.store, FakeWiki(tmp_path).snapshot("example/engineer"))
    engine.store.lock_scoring(run_id)
    monkeypatch.setattr(webapp, "engine", engine)
    webapp.report_tasks.clear()

    async def exercise():
        released = asyncio.Event()

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                released.set()

        task = asyncio.create_task(worker())
        webapp.report_tasks[run_id] = task
        await asyncio.sleep(0)
        result = await webapp.stop_report(run_id)
        assert result["stopped"] is True
        assert released.is_set() and task.cancelled()
        assert engine.store.get_run(run_id)["report_state"] == "interrupted"
        assert (await engine.state(run_id))["editable"] is False
        state_before = engine.store.get_run(run_id)
        assert (await webapp.stop_report(run_id))["stopped"] is False
        assert engine.store.get_run(run_id) == state_before
        webapp.report_tasks.clear()

    asyncio.run(exercise())


def test_coaching_rejects_model_instruction_echo():
    raw = {
        "fact_ids": ["f"],
        "why_it_works": "Uses confirmed work.",
        "outline": "Explain the action and verified result.",
        "next_action": "Return JSON with why_it_works, next_action and example_parts.",
        "example_parts": [{"slot": "action", "fact_id": "f"}],
    }
    with pytest.raises(ValueError, match="instructions"):
        validate_coaching(raw, {"f": "Built a test service."}, {"locale": "en", "category": "portfolio"})


def test_local_server_uses_configured_loopback_port_and_key(monkeypatch, tmp_path):
    import sys

    from interview_simulator import cli

    model = tmp_path / "model.gguf"
    model.write_bytes(b"synthetic")
    config = Settings(
        tmp_path,
        tmp_path / "InterviewWiki",
        tmp_path / ".simulator",
        "http://[::1]:8099/v1",
        model_path=model,
        model_api_key="synthetic-local-only",
    )
    monkeypatch.setattr(cli.Settings, "load", lambda: config)
    monkeypatch.setattr(cli.shutil, "which", lambda binary: "/synthetic/llama-server")
    captured = []
    monkeypatch.setattr(
        "interview_simulator.processes.serve_native", lambda command: captured.append(command)
    )
    monkeypatch.setattr(sys, "argv", ["interview-simulator", "local-server"])
    cli.main()
    command = captured[0]
    assert command[command.index("--port") + 1] == "8099"
    assert command[command.index("--host") + 1] == "::1"
    assert command[command.index("--api-key") + 1] == config.model_api_key
    monkeypatch.setattr(sys, "argv", ["interview-simulator", "local-server", "--port", "0"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_concurrent_credential_initialization_retains_one_vault_namespace(tmp_path):
    with ThreadPoolExecutor(4) as pool:
        profiles = list(pool.map(lambda _: Credentials(tmp_path), range(8)))
    assert len({profile.metadata["installation"] for profile in profiles}) == 1
    assert (
        json.loads((tmp_path / "credential-profiles.json").read_text())["installation"]
        == profiles[0].metadata["installation"]
    )


def test_adk_wrapper_cleans_up_on_normal_interrupt(monkeypatch, tmp_path):
    import uvicorn
    from click import Abort
    from google.adk.cli import fast_api

    from interview_simulator import adk_server

    def stopped(application, **kwargs):
        assert adk_server.BOOTSTRAP is not None
        assert kwargs["timeout_graceful_shutdown"] == 5
        raise Abort()

    monkeypatch.setattr(fast_api, "get_fast_api_app", lambda **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", stopped)
    adk_server.serve(settings(tmp_path), 8765, False)
    assert adk_server.BOOTSTRAP is None
    assert adk_server.CLOUD_ALLOWED is False


def test_installer_replaces_copied_environment_without_touching_private_files(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "setup_portability", Path(__file__).parents[1] / "scripts/setup_environment.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / "copy"
    activation = project / ".venv/bin/activate"
    activation.parent.mkdir(parents=True)
    activation.write_text("VIRTUAL_ENV='/previous/project/.venv'\n")
    private = project / ".env"
    private.write_text("PRIVATE=preserved\n")
    backup = module.prepare_environment(project, tmp_path / "retained")
    assert backup is not None and (backup / "bin/activate").is_file()
    assert not (project / ".venv").exists()
    assert private.read_text() == "PRIVATE=preserved\n"
    (project / ".venv").mkdir()
    module.stamp_environment(project)
    assert module.prepare_environment(project, tmp_path / "retained") is None
