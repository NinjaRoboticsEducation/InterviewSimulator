"""Fictional reference coverage; automated guards cannot certify translation meaning."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from interview_simulator.adk_runtime import LocalAdk
from interview_simulator.config import Settings
from interview_simulator.localization import numeric_values, validate_text
from interview_simulator.providers import ProviderError
from interview_simulator.questions import CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
CORPUS = json.loads((ROOT / "tests/fixtures/multilingual_intents.json").read_text(encoding="utf-8"))


def test_corpus_has_distinct_intents_and_honest_review_status():
    cases = CORPUS["cases"]
    assert CORPUS["fictional"] is True
    assert CORPUS["review_status"] == "awaiting-native-review"
    assert len({case["intent_id"] for case in cases}) == 30
    assert Counter(case["category"] for case in cases) == {category: 6 for category in CATEGORIES}
    assert {case["source_locale"] for case in cases} == {"en", "ja", "zh-Hant"}
    assert all(set(case["questions"]) == {"en", "ja", "zh-Hant"} for case in cases)
    assert {feature for case in cases for feature in case["features"]} >= {
        "terminology",
        "uncertainty",
        "negation",
        "dates",
        "numbers",
        "team_ownership",
        "missing_evidence",
    }


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["intent_id"])
def test_reference_questions_pass_all_language_pairs_without_changing_quantities(case):
    for source in case["questions"].values():
        for locale, target in case["questions"].items():
            result = validate_text(target, locale, source, tuple(CORPUS["protected_names"]))
            assert numeric_values(result) == numeric_values(source)
            for name in CORPUS["protected_names"]:
                assert (name in source) == (name in result)
            assert result.endswith(("?", "？", "。", "."))


@pytest.mark.parametrize("locale", ["en", "ja", "zh-Hant"])
def test_corpus_rejects_changed_metric_and_unfinished_answer_artifact(locale):
    case = next(case for case in CORPUS["cases"] if case["intent_id"] == "metric-attribution")
    question = case["questions"][locale]
    with pytest.raises(ValueError, match="changed a number"):
        validate_text(question.replace("20%", "30%"), locale, case["questions"]["en"])
    with pytest.raises(ValueError, match="placeholders"):
        validate_text(question + " [add verified result]", locale)


@pytest.mark.parametrize("bad_output", ['{"text":', '{"text": "[add answer]"}'])
def test_localization_repairs_malformed_or_unfinished_output_once(tmp_path, monkeypatch, bad_output):
    model = LocalAdk(Settings(ROOT, ROOT / "InterviewWiki", tmp_path))
    payloads = []

    async def response(_name, _instruction, payload, _schema):
        payloads.append(dict(payload))
        return bad_output if len(payloads) == 1 else '{"text": "自己紹介をお願いします。"}'

    monkeypatch.setattr(model, "_run_agent", response)
    result = asyncio.run(model.localize({"question": "Please introduce yourself.", "locale": "ja"}))
    assert result == "自己紹介をお願いします。"
    assert len(payloads) == 2 and "repair_error" in payloads[1]


def test_localization_exhausts_repair_without_accepting_malformed_output(tmp_path, monkeypatch):
    model = LocalAdk(Settings(ROOT, ROOT / "InterviewWiki", tmp_path))
    calls = []

    async def response(*_args):
        calls.append(True)
        return '{"text":'

    monkeypatch.setattr(model, "_run_agent", response)
    with pytest.raises(ValueError):
        asyncio.run(model.localize({"question": "Please introduce yourself.", "locale": "ja"}))
    assert len(calls) == 2


def test_localization_does_not_repair_or_retry_provider_quota(tmp_path, monkeypatch):
    model = LocalAdk(Settings(ROOT, ROOT / "InterviewWiki", tmp_path))
    calls = []

    async def response(*_args):
        calls.append(True)
        raise ProviderError("Fictional quota failure", code="RATE_LIMITED", dispatch="sent")

    monkeypatch.setattr(model, "_run_agent", response)
    with pytest.raises(ProviderError) as failure:
        asyncio.run(model.localize({"question": "Please introduce yourself.", "locale": "ja"}))
    assert failure.value.code == "RATE_LIMITED" and len(calls) == 1


def test_release_includes_fictional_corpus_and_excludes_private_canaries(tmp_path):
    spec = importlib.util.spec_from_file_location("release_builder", ROOT / "scripts/build_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source"
    source.mkdir()
    public = source / "tests/fixtures/multilingual_intents.json"
    public.parent.mkdir(parents=True)
    public.write_text(json.dumps(CORPUS, ensure_ascii=False), encoding="utf-8")
    canary = "FICTIONAL_PRIVATE_RELEASE_CANARY"
    for relative in (".env", ".simulator/settings.json", "InterviewWiki/Output/private.md", "doc/prompt.md"):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canary, encoding="utf-8")
    # Isolate the tracked-file inventory without requiring a nested Git repository.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            module.subprocess, "check_output", lambda *_args, **_kwargs: b"InterviewWiki/Output/private.md\0"
        )
        destination = tmp_path / "release"
        result = module.build(source, destination)
    assert result["files"] == 1
    assert (destination / "tests/fixtures/multilingual_intents.json").exists()
    assert all(
        canary not in file.read_text(encoding="utf-8") for file in destination.rglob("*") if file.is_file()
    )
