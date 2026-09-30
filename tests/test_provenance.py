from __future__ import annotations

import asyncio

import httpx
import pytest

from interview_simulator.config import Settings
from interview_simulator.provenance import model_identity


def test_loaded_model_matches_file_and_hash(monkeypatch, tmp_path):
    model = tmp_path / "small.gguf"
    model.write_bytes(b"synthetic GGUF")
    original = httpx.AsyncClient
    paths = []

    class MockClient(original):
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False
            super().__init__(**kwargs, transport=httpx.MockTransport(self.reply))

        def reply(self, request):
            paths.append(str(request.url))
            return httpx.Response(200, json={"model_path": str(model)})

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    settings = Settings(tmp_path, tmp_path, tmp_path / "state", model_path=model)
    identity = asyncio.run(model_identity(settings))
    assert identity["gguf_file"] == "small.gguf"
    assert identity["gguf_sha256"].startswith("sha256:")
    assert paths == ["http://127.0.0.1:8081/props"]


def test_mismatched_loaded_model_stops_assessment(monkeypatch, tmp_path):
    one, two = tmp_path / "one.gguf", tmp_path / "two.gguf"
    one.write_bytes(b"one")
    two.write_bytes(b"two")
    original = httpx.AsyncClient

    class MockClient(original):
        def __init__(self, **kwargs):
            super().__init__(
                **kwargs,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"model_path": str(two)})
                ),
            )

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    with pytest.raises(ValueError, match="differs"):
        asyncio.run(model_identity(Settings(tmp_path, tmp_path, tmp_path / "state", model_path=one)))


def test_assessment_records_model_prompt_and_invocation(monkeypatch, tmp_path):
    import json

    from interview_simulator.adk_runtime import LocalAdk

    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    adapter = LocalAdk(Settings(tmp_path, tmp_path, tmp_path / "state", model_path=model))
    calls = []

    async def fake_identity(settings):
        return {"model_alias": "interview-local", "gguf_file": "model.gguf", "gguf_sha256": "sha256:abc"}

    async def fake_agent(name, instruction, payload, schema, invocation_id=None):
        calls.append(invocation_id)
        return json.dumps(
            {
                "scores": {
                    key: 3 for key in ("relevance", "specificity", "reasoning", "clarity", "reflection")
                },
                "quote": "Answer",
                "strength": "Clear",
                "improvement": "Give results",
                "reason": "Relevant",
                "fact_ids": [],
            }
        )

    monkeypatch.setattr("interview_simulator.adk_runtime.model_identity", fake_identity)
    monkeypatch.setattr(adapter, "_run_agent", fake_agent)
    result = asyncio.run(
        adapter.evaluate(
            {"locale": "en", "text": "Question", "category": "role"}, "Answer", {}, "requirement"
        )
    )
    assert result["provenance"]["gguf_sha256"] == "sha256:abc"
    assert result["provenance"]["prompt_sha256"].startswith("sha256:")
    assert result["provenance"]["invocation_id"] == calls[0]
    assert result["provenance"]["rubric_version"] == "fixed-five-dimensions-v1"
