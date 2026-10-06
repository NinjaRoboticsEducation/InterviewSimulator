"""Fictional regressions for calendar translation and preparation repair."""

from __future__ import annotations

import asyncio
import json

import pytest
from test_interview_flow import make_engine

from interview_simulator.adk_runtime import LocalAdk
from interview_simulator.config import Settings
from interview_simulator.errors import safe_failure
from interview_simulator.localization import (
    LocalizationValidationError,
    calendar_dates,
    numeric_values,
    validate_text,
)
from interview_simulator.providers import ProviderService


@pytest.mark.parametrize(
    "locale,text",
    [
        ("ja", "2021年8月から2024年9月までの経験について教えてください。"),
        ("zh-Hant", "請說明2021年8月至2024年9月的經驗。"),
        ("en", "Please explain your experience from 2021-08 to 2024-09."),
    ],
)
def test_named_months_equal_numeric_months(locale, text):
    source = "Please explain your experience from August 2021 to September 2024."
    assert validate_text(text, locale, source) == text
    assert numeric_values(source) == numeric_values(text)


@pytest.mark.parametrize("source", ["Aug. 5, 2021", "5 August 2021", "August 5th, 2021", "2021-08-05"])
def test_calendar_day_formats(source):
    assert calendar_dates(source) == calendar_dates("2021年8月5日")
    assert validate_text("2021年8月5日について教えてください。", "ja", source)


def test_swapped_months_are_rejected_even_when_number_sets_match():
    source = "From August 2021 to September 2024."
    wrong = "2021年9月から2024年8月までの経験を教えてください。"
    assert numeric_values(source) == numeric_values(wrong)
    with pytest.raises(LocalizationValidationError, match="calendar date"):
        validate_text(wrong, "ja", source)
    with pytest.raises(LocalizationValidationError, match="number"):
        validate_text("2021年8月から2025年9月までの経験です。", "ja", source)


def test_month_named_person_does_not_become_a_number():
    assert numeric_values("May supported the team.") == set()
    assert numeric_values("The team may support one project.") == {"1"}


@pytest.mark.parametrize("locale", ["ja", "zh-Hant"])
def test_repair_includes_rejected_english_and_keeps_date_checks(tmp_path, monkeypatch, locale):
    model = LocalAdk(Settings(tmp_path, tmp_path / "InterviewWiki", tmp_path / ".simulator"))
    payloads = []
    untranslated = "Senior Research Designer at Fictional Studio"
    fixed = {
        "ja": "2021年8月の研究デザイナーの経験を教えてください。",
        "zh-Hant": "請說明2021年8月擔任研究設計師的經驗。",
    }[locale]

    async def response(name, instruction, payload, schema):
        payloads.append(dict(payload))
        assert "job titles" in instruction
        return (
            json.dumps({"text": untranslated + "（August 2021）の経験です。"})
            if len(payloads) == 1
            else json.dumps({"text": fixed})
        )

    monkeypatch.setattr(model, "_run_agent", response)
    source = untranslated + " (August 2021)."
    assert asyncio.run(model.localize({"question": source, "locale": locale, "ordinal": 2})) == fixed
    assert untranslated in payloads[1]["previous_output"]
    assert "repair_policy" in payloads[1]


def test_exhausted_translation_has_safe_stage_reason_and_question(tmp_path, monkeypatch):
    model = LocalAdk(Settings(tmp_path, tmp_path / "InterviewWiki", tmp_path / ".simulator"))

    async def response(*args):
        return json.dumps({"text": "Private Career Claim Is Still English の経験です。"})

    monkeypatch.setattr(model, "_run_agent", response)
    with pytest.raises(LocalizationValidationError) as error:
        asyncio.run(model.localize({"question": "Private original", "locale": "ja", "ordinal": 5}))
    diagnostic = safe_failure(error.value)
    assert diagnostic["reason"] == "UNTRANSLATED_PASSAGE"
    assert diagnostic["stage"] == "localization" and diagnostic["ordinal"] == 5
    assert "Private" not in json.dumps(diagnostic)


@pytest.mark.parametrize("locale", ["en", "ja", "zh-Hant"])
@pytest.mark.parametrize("generated", [False, True])
def test_full_preparation_with_dated_profile_reaches_first_question(tmp_path, monkeypatch, locale, generated):
    async def exercise():
        engine = make_engine(tmp_path)
        source = "Research designer at Fictional Studio (August 2021 – September 2024)."
        snapshot = engine.wiki.snapshot("example/engineer")
        snapshot["inputs"]["candidate"]["facts"][0]["statement"] = source
        monkeypatch.setattr(engine.wiki, "snapshot", lambda _: snapshot)
        engine.providers = ProviderService(engine.settings)
        engine.providers.plan = engine.providers.plan.model_copy(update={"generate_questions": generated})

        async def validate(*args):
            pass

        monkeypatch.setattr(engine.providers, "validate", validate)

        async def identity(*args):
            return {"model": "fictional-test"}

        monkeypatch.setattr(LocalAdk, "_identity", identity)

        async def response(self, name, instruction, payload, schema):
            if name == "question_designer":
                return json.dumps(
                    {"questions": [{"ordinal": n, "focus": "baseline", "fact_id": ""} for n in range(1, 11)]}
                )
            assert name == "content_localizer"
            translation = {
                "ja": "架空スタジオの研究デザイナー（2021年8月〜2024年9月）",
                "zh-Hant": "虛構工作室的研究設計師（2021年8月至2024年9月）",
            }[locale]
            text = (
                payload["question"]
                .replace(source, translation)
                .replace("Engineer", {"ja": "エンジニア", "zh-Hant": "工程師"}[locale])
                .replace("Python delivery", {"ja": "Pythonの開発", "zh-Hant": "Python開發"}[locale])
            )
            assert 1 <= payload["ordinal"] <= 10
            return json.dumps({"text": text})

        monkeypatch.setattr(LocalAdk, "_run_agent", response)
        state = await engine.start("example/engineer", locale)
        assert state["status"] == "active" and state["question"]["ordinal"] == 1
        run = engine.store.get_run(state["run_id"])
        assert len(run["questions"]) == 10 and run["preparation_error"] is None
        assert snapshot["inputs"]["candidate"]["facts"][0]["statement"] == source

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "damage",
    [
        "{",
        '{"text": 42}',
        '{"version": "question-localization-v2", "text": "An untranslated English sentence remains."}',
    ],
)
def test_invalid_translation_cache_is_regenerated(tmp_path, damage):
    from dataclasses import replace

    from test_interview_flow import FakeWiki

    from interview_simulator.localization import VERSION, Localizer
    from interview_simulator.questions import make_fixed_questions

    async def exercise():
        class Model:
            calls = 0

            async def _identity(self, _task):
                return {"model": "fictional-test"}

            async def localize(self, payload):
                self.calls += 1
                return "自己紹介をお願いします。"

        model = Model()

        async def invoke(fn, payload):
            return await fn(payload)

        snapshot = FakeWiki(tmp_path).snapshot("example/engineer")
        questions = [replace(q, localization_version=VERSION) for q in make_fixed_questions(snapshot, "ja")]
        questions[0] = replace(questions[0], text="Please introduce yourself.", localization_version=None)
        localizer = Localizer(tmp_path, model, invoke)
        await localizer.questions(snapshot, questions)
        cache = next((tmp_path / "translation-cache").glob("*.json"))
        cache.write_text(damage)
        repaired = await localizer.questions(snapshot, questions)
        assert model.calls == 2 and repaired[0].text == "自己紹介をお願いします。"
        assert json.loads(cache.read_text())["version"] == VERSION
        await localizer.questions(snapshot, questions)
        assert model.calls == 2

    asyncio.run(exercise())
