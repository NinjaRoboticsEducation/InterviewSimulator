from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from test_interview_flow import FakeWiki, make_engine
from test_refinement import answered, settings

from interview_simulator.context_budget import answer_spans, compact_facts
from interview_simulator.errors import InputBudgetError
from interview_simulator.evaluation import validate_coaching
from interview_simulator.localization import Localizer, validate_text
from interview_simulator.providers import Binding, ModelPlan, ProviderError, ProviderService
from interview_simulator.providers.ollama import ConnectionRequest, normalize_endpoint
from interview_simulator.questions import make_fixed_questions
from interview_simulator.storage import Store


def test_preparation_failure_retry_is_distinct_from_cancellation(tmp_path, monkeypatch):
    async def exercise():
        engine = make_engine(tmp_path)

        async def fail(*_args):
            raise InputBudgetError("Synthetic oversized preparation")

        monkeypatch.setattr(engine, "_localize_preparation", fail)
        state = await engine.start("example/engineer", "ja", request_id="a" * 32)
        assert state["status"] == "preparation_failed"
        assert state["question"] is None and state["greeting"] is None
        assert state["preparation_error"]["code"] == "INPUT_TOO_LARGE"
        replay = await engine.start("example/engineer", "ja", request_id="a" * 32)
        assert replay["run_id"] == state["run_id"]
        with engine.store.connect() as db:
            assert db.execute("SELECT count(*) FROM presentations").fetchone()[0] == 0
        ready = await engine.retry_preparation(state["run_id"], baseline=True)
        assert ready["status"] == "active" and ready["question"]
        assert "Built" not in ready["question"]["text"]

    asyncio.run(exercise())


def test_context_selection_preserves_whole_linked_statements(tmp_path):
    snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
    questions = make_fixed_questions(snapshot, "en")
    facts = snapshot["inputs"]["candidate"]["facts"]
    facts.extend(
        {"fact_id": str(i), "statement": "irrelevant " * 1000, "confidence": "confirmed", "sensitive": False}
        for i in range(66)
    )
    selected = compact_facts(snapshot, questions, limit=2)
    assert all(len(value) < 1000 for value in selected.values())
    answer = "A sentence.\n 改善しました。\n我協助團隊。"
    assert all(span in answer for span in answer_spans(answer).values())


@pytest.mark.parametrize(
    "locale,text,source",
    [
        ("ja", "2件のチーム案件を支援しました。", "I supported 3 projects."),
        ("zh-Hant", "我協助了3個專案。[add result]", "3 projects"),
        ("ja", "経験は Built a large test service for clients です。", ""),
    ],
)
def test_localization_rejects_changed_metrics_placeholders_and_english(locale, text, source):
    with pytest.raises(ValueError):
        validate_text(text, locale, source)


def test_translation_cache_is_private_and_model_scoped(tmp_path):
    async def exercise():
        calls = []

        class Model:
            async def _identity(self, _task):
                return {"model": "synthetic-v1"}

            async def localize(self, payload):
                calls.append(payload)
                return "自己紹介をお願いします。"

        async def invoke(fn, *args):
            return await fn(*args)

        snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
        # One translation, remaining questions already frozen/validated.
        questions = [
            replace(q, localization_version="question-localization-v1")
            for q in make_fixed_questions(snapshot, "ja")
        ]
        questions[0] = replace(questions[0], text="Please introduce yourself.", localization_version=None)
        localizer = Localizer(tmp_path, Model(), invoke)
        result = await localizer.questions(snapshot, questions)
        assert result[0].original_text == "Please introduce yourself."
        await localizer.questions(snapshot, questions)
        assert len(calls) == 1
        assert next((tmp_path / "translation-cache").glob("*.json")).stat().st_mode & 0o077 == 0

    asyncio.run(exercise())


def test_rate_limit_pauses_report_without_losing_score(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        run_id = answered(engine.store, engine.wiki.snapshot("example/engineer"))
        calls = []

        class Assessor:
            async def evaluate(self, *_args):
                calls.append("score")
                return {
                    "score": 75,
                    "scores": {},
                    "quote": "Answer 1",
                    "strength": "Clear",
                    "improvement": "Expand",
                    "reason": "Relevant",
                    "fact_ids": [],
                }

            async def coach(self, *_args):
                calls.append("coach")
                raise ProviderError("Synthetic quota", code="RATE_LIMITED", retry_after=60, dispatch="sent")

        engine.adk = Assessor()
        report = await engine.evaluate(run_id)
        run = engine.store.get_run(run_id)
        assert calls == ["score", "coach"]
        assert run["evaluations"][1]["score"] == 75
        assert run["report_state"] == "retry_wait" and report.exists()
        with pytest.raises(ProviderError, match="retry delay"):
            await engine.evaluate(run_id)
        assert calls == ["score", "coach"]

    asyncio.run(exercise())


def test_report_revisions_and_allowance_are_durable_and_idempotent(tmp_path):
    store = Store(tmp_path / "bank.sqlite")
    snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
    run_id = answered(store, snapshot)
    frozen = store.lock_scoring(run_id)
    store.save_evaluation(run_id, 1, {"score": 55})
    store.report_state(run_id, "incomplete")
    revision = store.get_run(run_id)["revision"]
    store.grant_recovery(run_id, "allowance", revision)
    store.grant_recovery(run_id, "allowance", revision)
    assert store.get_run(run_id)["extra_calls"] == 12
    store.new_assessment_revision(run_id, ModelPlan().model_dump(), revision + 1, "new-report")
    store.new_assessment_revision(run_id, ModelPlan().model_dump(), revision + 1, "new-report")
    reopened = Store(store.path)
    assert reopened.get_run(run_id)["assessment_version"] == 1
    assert reopened.get_run(run_id)["evaluations"] == {}
    assert reopened.lock_scoring(run_id) == frozen
    with reopened.connect() as db:
        assert (
            json.loads(db.execute("SELECT payload_json FROM assessment_revisions").fetchone()[0])[
                "evaluations"
            ]["1"]["score"]
            == 55
        )


@pytest.mark.parametrize(
    "mode,url",
    [
        ("local", "http://192.168.0.2:11434"),
        ("local", "http://127.0.0.1@evil.test"),
        ("local", "https://localhost"),
        ("local", "http://localhost/api"),
        ("cloud", "https://evil.test"),
        ("cloud", "http://ollama.com"),
        ("local", "http://127.0.0.1?key=secret"),
    ],
)
def test_ollama_rejects_untrusted_destinations(mode, url):
    with pytest.raises(ValueError):
        normalize_endpoint(mode, url)


def test_ollama_local_native_api_and_cloud_alias_consent(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": "synthetic"})
        if path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "qwen3.5:4b", "digest": "sha256:abc"},
                        {"name": "remote", "digest": "sha256:xyz"},
                    ]
                },
            )
        if path == "/api/show":
            name = json.loads(request.content)["model"]
            return httpx.Response(
                200,
                json={
                    "capabilities": ["completion", "thinking"],
                    "thinking": {"values": [False, True], "default": True},
                    "details": {"quantization_level": "Q4_K_M"},
                    **(
                        {"remote_host": "https://ollama.com", "remote_model": "qwen-cloud"}
                        if name == "remote"
                        else {}
                    ),
                },
            )
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:4b", "context_length": 4096}]})
        assert path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False and body["think"] is False and isinstance(body["format"], dict)
        assert "Authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": '{"ok":true}', "thinking": "never retained"},
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    async def exercise():
        service = ProviderService(settings(tmp_path), httpx.MockTransport(handler))
        connected = await service.ollama.connect(
            ConnectionRequest(mode="local", endpoint="http://localhost:11434")
        )
        binding = Binding(
            provider="ollama", model="qwen3.5:4b", connection=connected["connection"]["id"], locality="local"
        )
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        assert json.loads(await service.generate(binding, "Return ok=true.", "synthetic", schema)) == {
            "ok": True
        }
        assert "never retained" not in json.dumps(service.last_call)
        assert service.last_call["model_digest"] == "sha256:abc"
        with pytest.raises(ValueError, match="locality changed"):
            await service.ollama.validate(binding.model_copy(update={"model": "remote"}))
        remote = binding.model_copy(update={"model": "remote", "locality": "cloud"})
        with pytest.raises(ValueError, match="representative"):
            await service.ollama.validate(remote)
        assert ModelPlan(evaluation=remote).cloud_providers == {"ollama"}

    asyncio.run(exercise())
    assert all(request.url.host == "127.0.0.1" for request in calls)


def test_finished_coaching_rejects_unverified_metrics():
    raw = {
        "fact_ids": ["f"],
        "why_it_works": "Specific contribution",
        "outline": "State my contribution",
        "next_action": "Verify the outcome",
        "example_clauses": [{"text": "I improved revenue by 900%.", "kind": "fact", "fact_ids": ["f"]}],
    }
    with pytest.raises(ValueError, match="metric"):
        validate_coaching(raw, {"f": "Built a test service."}, {"locale": "en", "category": "portfolio"})
    raw["example_clauses"] = [
        {"text": "I built a test service.", "kind": "fact", "fact_ids": ["f"]},
        {
            "text": "I would verify the outcome with the team before claiming a result.",
            "kind": "prospective",
            "fact_ids": [],
        },
    ]
    result = validate_coaching(raw, {"f": "Built a test service."}, {"locale": "en", "category": "portfolio"})
    assert "[" not in result["example"]


@pytest.mark.parametrize(
    "locale,text",
    [
        ("en", "I supported 3 projects."),
        ("ja", "三つの案件を支援しました。"),
        ("zh-Hant", "我協助了三個專案。"),
    ],
)
def test_written_numbers_preserve_quantities(locale, text):
    assert validate_text(text, locale, "I supported three projects.") == text
    with pytest.raises(ValueError, match="number"):
        validate_text(text, locale, "I supported four projects.")


def test_committed_export_rejects_orphans_and_detects_damage(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        run_id = answered(engine.store, engine.wiki.snapshot("example/engineer"))
        for ordinal in range(1, 11):
            engine.store.save_evaluation(
                run_id,
                ordinal,
                {
                    "score": 75,
                    "scores": dict.fromkeys(
                        ("relevance", "specificity", "reasoning", "clarity", "reflection"), 3
                    ),
                    "strength": "Clear contribution",
                    "improvement": "Verify an outcome",
                    "reason": "Relevant",
                    "fact_ids": [],
                    "quote": f"Answer {ordinal}",
                    "coaching": {
                        "example": "Fictional example",
                        "why_it_works": "Honest",
                        "outline": "Action",
                        "next_action": "Practise",
                        "fact_ids": [],
                    },
                },
            )
        report = await engine.evaluate(run_id)
        orphan = report.with_name("report-r99.md")
        orphan.write_text("incomplete export")
        assert engine.latest_report(run_id) == report
        report.write_text("damaged report")
        with pytest.raises(ValueError, match="damaged"):
            engine.latest_report(run_id)
        repaired = await engine.evaluate(run_id)
        assert repaired.name == "report-r100.md" and report.read_text() == "damaged report"
        assert engine.latest_report(run_id) == repaired
        revision = engine.store.get_run(run_id)["revision"]
        engine.store.new_assessment_revision(run_id, ModelPlan().model_dump(), revision, "revision-id")
        assert engine.latest_report(run_id) is None
        assert repaired.is_file()

    asyncio.run(exercise())


def test_recovery_request_cannot_be_reused_for_different_action(tmp_path):
    store = Store(tmp_path / "bank.sqlite")
    run_id = answered(store, FakeWiki(tmp_path).snapshot("example/engineer"))
    store.lock_scoring(run_id)
    store.report_state(run_id, "incomplete")
    store.grant_recovery(run_id, "same-id", store.get_run(run_id)["revision"])
    with pytest.raises(ValueError, match="different"):
        store.new_assessment_revision(
            run_id, ModelPlan().model_dump(), store.get_run(run_id)["revision"], "same-id"
        )


def test_model_fingerprints_accept_identical_copies_reject_mismatch(tmp_path, monkeypatch):
    from interview_simulator.provenance import model_identity

    source, loaded = tmp_path / "configured.gguf", tmp_path / "loaded.gguf"
    source.write_bytes(b"fictional model bytes")
    loaded.write_bytes(source.read_bytes())
    original = httpx.AsyncClient

    class Client(original):
        def __init__(self, **kwargs):
            super().__init__(
                **kwargs,
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json={"model_path": str(loaded)})
                ),
            )

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    config = replace(settings(tmp_path), model_path=source)
    assert asyncio.run(model_identity(config))["gguf_sha256"].startswith("sha256:")
    loaded.write_bytes(b"different model bytes")
    with pytest.raises(ValueError, match="differs"):
        asyncio.run(model_identity(config))


@pytest.mark.parametrize("negative_supported", [False, True])
def test_ollama_qualification_requires_all_tasks_and_rejects_invention(
    tmp_path, monkeypatch, negative_supported
):
    from interview_simulator.adk_runtime import COACHING_SCHEMA, EVALUATION_SCHEMA
    from interview_simulator.providers.ollama import QUALIFICATION_VERSION

    service = ProviderService(settings(tmp_path))
    connection = "c" * 32
    service.ollama.profiles[connection] = {
        "id": connection,
        "mode": "cloud",
        "endpoint": "https://ollama.com",
        "credential": None,
        "context_tokens": 4096,
        "qualified": {"fictional-cloud": {"version": QUALIFICATION_VERSION, "digest": "old"}},
    }
    binding = Binding(provider="ollama", model="fictional-cloud", connection=connection, locality="cloud")
    calls = []

    async def inspect(_):
        return {"digest": "fictional-digest", "structured_output": "application-validated JSON"}

    async def generate(_binding, instruction, prompt, schema):
        calls.append(schema)
        payload = json.loads(prompt)
        locale = payload.get("locale", "en")
        wording = {
            "en": "Verify a result before using it.",
            "ja": "結果を確認してから説明してください。",
            "zh-Hant": "請先核對成果再使用。",
        }[locale]
        if schema == EVALUATION_SCHEMA:
            return json.dumps(
                {
                    "scores": dict.fromkeys(
                        ("relevance", "specificity", "reasoning", "clarity", "reflection"), 3
                    ),
                    "quote_span_id": "s1",
                    "strength": wording,
                    "improvement": wording,
                    "reason": wording,
                    "fact_ids": ["f"],
                }
            )
        if schema == COACHING_SCHEMA:
            return json.dumps(
                {
                    "example_clauses": [
                        {"text": payload["answer"], "kind": "fact", "fact_ids": ["f"]},
                        {
                            "text": {
                                "en": "I am interested in discussing this contribution.",
                                "ja": "この貢献についてお話ししたいです。",
                                "zh-Hant": "我有興趣分享這項貢獻。",
                            }[locale],
                            "kind": "motivation",
                            "fact_ids": [],
                        },
                    ],
                    "fact_ids": ["f"],
                    "why_it_works": wording,
                    "outline": wording,
                    "next_action": wording,
                }
            )
        if "supported" in schema["properties"]:
            return json.dumps({"supported": negative_supported})
        return json.dumps(
            {
                "text": {
                    "ja": "私は二つのチーム案件を支援し、率いてはいません。どのように貢献しましたか。",
                    "zh-Hant": "我協助了兩個團隊專案，並未領導。我的貢獻是什麼？",
                }[locale]
            }
        )

    monkeypatch.setattr(service.ollama, "inspect", inspect)
    monkeypatch.setattr(service, "generate", generate)
    if negative_supported:
        with pytest.raises(ValueError, match="unsupported-claim"):
            asyncio.run(service.probe_ollama(binding))
        assert not service.ollama.profiles[connection]["qualified"]
    else:
        assert asyncio.run(service.probe_ollama(binding))["checks"] == 9
        assert service.ollama.profiles[connection]["qualified"][binding.model]["digest"] == "fictional-digest"
    assert len(calls) == 9
