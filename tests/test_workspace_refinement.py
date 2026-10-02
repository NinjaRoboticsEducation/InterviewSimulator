from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

import pytest
from test_interview_flow import make_engine
from test_refinement import answered

from interview_simulator.coaching import CoachingValidationError, evidence_packet, example_count, has_example
from interview_simulator.evaluation import validate_coaching
from interview_simulator.portability import recover_report
from interview_simulator.providers import ProviderService
from interview_simulator.speech import Speech


def raw_example(kind, text, ids=None):
    return {
        "fact_ids": ids or [],
        "example_clauses": [{"text": text, "kind": kind, "fact_ids": ids or []}],
        "why_it_works": "Clear intent.",
        "outline": "Intent and contribution.",
        "next_action": "Adapt this to your own goals.",
    }


@pytest.mark.parametrize(
    "kind,text",
    [
        ("motivation", "I am interested in learning how the team works."),
        ("prospective", "I would use my first 30 days to understand the team's priorities."),
        ("question", "How does the team decide which design problems to prioritize?"),
        ("bridge", "Let me explain my approach."),
    ],
)
def test_natural_nonhistorical_clauses_do_not_require_keyword_or_career_citation(kind, text):
    result = validate_coaching(raw_example(kind, text), {}, {"locale": "en"})
    assert result["example"] == text and result["fact_ids"] == []


def test_company_evidence_cannot_be_used_as_candidate_experience():
    q = {"locale": "en", "company_evidence": {"company:c": "The company builds transport services."}}
    raw = raw_example("company", "The company builds transport services.", ["company:c"])
    result = validate_coaching(raw, {}, q)
    assert result["source_ids"] == ["company:c"] and result["fact_ids"] == []
    raw["example_clauses"][0]["kind"] = "fact"
    with pytest.raises(CoachingValidationError, match="CANDIDATE_CITATION"):
        validate_coaching(raw, {}, q)


def test_unknown_sources_and_unsupported_career_numbers_still_rejected():
    with pytest.raises(ValueError):
        validate_coaching(raw_example("company", "Company detail", ["unknown"]), {}, {"locale": "en"})
    with pytest.raises(ValueError, match="metric"):
        validate_coaching(
            raw_example("fact", "I delivered 900 projects.", ["f"]),
            {"f": "I supported a project."},
            {"locale": "en"},
        )


def test_evidence_selection_prefers_question_links_and_primary_company_sources():
    snapshot = {
        "inputs": {
            "requirements": {"requirements": [{"requirement_id": "r", "statement": "Design services"}]},
            "research": {
                "sources": [
                    {
                        "source_id": "s",
                        "source_tier": "official",
                        "claim_type": "direct",
                        "excerpt": "Builds services",
                    },
                    {"source_id": "bad", "source_tier": "rumor", "excerpt": "Invented"},
                ]
            },
        }
    }
    facts = {"a": "Other work", "z": "Service design"}
    chosen, question = evidence_packet(
        snapshot,
        {
            "text": "Tell us about service design",
            "fact_ids": ["z"],
            "requirement_ids": ["r"],
            "source_ids": ["s"],
        },
        facts,
    )
    assert next(iter(chosen)) == "z"
    assert question["company_evidence"] == {
        "requirement:r": "Design services",
        "company:s": "Builds services",
    }


@pytest.mark.parametrize("locale", ["en", "ja", "zh-Hant"])
def test_skipped_questions_require_examples_and_resume_keeps_scores(tmp_path, locale):
    class Assessor:
        fail = True

        def __init__(self):
            self.calls = []

        async def evaluate(self, *args):
            raise AssertionError("Skipped answers must not be sent for scoring")

        async def coach(self, question, answer, facts, assessment):
            self.calls.append(question["ordinal"])
            assert assessment["skipped"] and assessment["score"] == 0
            if question["ordinal"] == 8 and self.fail:
                raise CoachingValidationError("UNSUPPORTED_CLAIM", 0)
            text = {
                "en": "I would first clarify the requirements.",
                "ja": "まず要件を確認したいと考えています。",
                "zh-Hant": "我會先確認需求。",
            }[locale]
            return {
                "example": text,
                "why_it_works": text,
                "outline": text,
                "next_action": text,
                "fact_ids": [],
            }

    async def exercise():
        engine = make_engine(tmp_path)
        engine.adk = Assessor()
        snapshot = engine.wiki.snapshot("example/engineer")
        from interview_simulator.questions import make_fixed_questions

        rid = engine.store.create_run(
            "example/engineer", locale, snapshot, make_fixed_questions(snapshot, locale)
        )
        for n in range(1, 11):
            engine.store.present(rid, n)
            engine.store.acknowledge_presentation(rid, n, f"{rid}-q{n:02d}")
            engine.store.submit(rid, n, f"s{n}", "", skipped=True)
        draft = await engine.evaluate(rid)
        before = engine.store.get_run(rid)
        assert example_count(before) == 9 and before["report_state"] == "incomplete"
        assert before["evaluations"][8]["coaching_failure"]["reason"] == "UNSUPPORTED_CLAIM"
        original = draft.read_bytes()
        engine.adk.fail = False
        report = await engine.evaluate(rid)
        after = engine.store.get_run(rid)
        assert after["report_state"] == "complete" and example_count(after) == 10
        assert engine.adk.calls == list(range(1, 11)) + [8]
        assert all(e["score"] == 0 for e in after["evaluations"].values())
        assert report != draft and draft.read_bytes() == original
        assert json.loads((report.parent / "simulation-manifest.json").read_text())["example_contract"] == 4

    asyncio.run(exercise())


def test_blank_example_never_counts_as_complete():
    assert not has_example({"example": " "})
    assert not has_example({"example": "Filled", "fact_ids": []})


def test_browser_segment_clips_at_limit_and_reports_it(tmp_path, monkeypatch):
    model = tmp_path / "model.bin"
    model.write_bytes(b"fictional")
    monkeypatch.setattr("interview_simulator.speech.shutil.which", lambda _: "/synthetic")

    def command(args, **kwargs):
        if args[0] == "ffmpeg":
            with wave.open(str(args[-1]), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\0\0" * (181 * 16000))
        else:
            with wave.open(args[args.index("-f") + 1], "rb") as audio:
                assert audio.getnframes() == 180 * 16000
            Path(args[args.index("-of") + 1] + ".txt").write_text("Fictional spoken answer")

    monkeypatch.setattr("interview_simulator.speech.subprocess.run", command)
    speech = Speech()
    speech.model_path = model
    assert speech.transcribe_segment(b"synthetic", "en") == {
        "text": "Fictional spoken answer",
        "limited": True,
        "limit_seconds": 180,
    }


def test_terminal_allowance_preserves_answers_and_requires_stopped_server(tmp_path, monkeypatch):
    from filelock import FileLock, Timeout

    engine = make_engine(tmp_path)
    monkeypatch.setattr("interview_simulator.engine.WikiAdapter", lambda _: engine.wiki)
    rid = answered(engine.store, engine.wiki.snapshot("example/engineer"))
    engine.store.report_state(rid, "incomplete")
    before = engine.store.get_run(rid)["answers"]
    result = recover_report(engine.settings, rid, revise=False, cloud_consent=False)
    assert result["action"] == "twelve_more_attempts"
    assert engine.store.get_run(rid)["answers"] == before
    with FileLock(engine.settings.state_root / "server.lock"), pytest.raises(Timeout):
        recover_report(engine.settings, rid, revise=False, cloud_consent=False)


def test_terminal_revision_requires_explicit_cloud_consent(tmp_path, monkeypatch):
    from interview_simulator.providers import Binding
    from interview_simulator.providers.credentials import save_private_json

    engine = make_engine(tmp_path)
    monkeypatch.setattr("interview_simulator.engine.WikiAdapter", lambda _: engine.wiki)
    rid = answered(engine.store, engine.wiki.snapshot("example/engineer"))
    engine.store.report_state(rid, "incomplete")
    service = ProviderService(engine.settings)
    plan = service.plan.model_copy(update={"coaching": Binding(provider="google", model="fictional")})
    save_private_json(service.path, plan.model_dump())
    with pytest.raises(ValueError, match="allow-cloud-text"):
        recover_report(engine.settings, rid, revise=True, cloud_consent=False)
    assert engine.store.get_run(rid)["assessment_version"] == 0
