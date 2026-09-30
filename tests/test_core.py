from __future__ import annotations

import pytest

from interview_simulator.evaluation import validate_coaching, validate_evaluation
from interview_simulator.questions import make_fixed_questions, validate_questions
from interview_simulator.report import render_report
from interview_simulator.storage import Store


@pytest.fixture
def snapshot():
    return {
        "reference": "example/engineer",
        "company": "Example",
        "role": "Engineer",
        "hashes": {"candidate": "sha256:a", "requirements": "sha256:b"},
        "inputs": {
            "candidate": {
                "facts": [
                    {
                        "fact_id": "fact-abc",
                        "statement": "Built a test service.",
                        "confidence": "confirmed",
                        "sensitive": False,
                    }
                ]
            },
            "requirements": {
                "requirements": [
                    {"requirement_id": "req-abc", "statement": "Python delivery", "priority": "high"}
                ]
            },
        },
    }


def test_ten_questions_each_locale_and_coverage(snapshot):
    for locale in ("en", "ja", "zh-Hant"):
        questions = make_fixed_questions(snapshot, locale)
        assert len(questions) == 10
        assert questions[0].category == "personal"
        assert questions[-1].category == "company"
        with pytest.raises(ValueError, match="ten scored"):
            validate_questions(questions[:-1], {"fact-abc"}, {"req-abc"})


def test_questions_use_frozen_candidate_and_company_evidence(snapshot):
    snapshot["inputs"]["research"] = {
        "sources": [
            {
                "source_id": "research-official",
                "source_tier": "official",
                "claim_type": "direct",
                "excerpt": "Our team is improving delivery quality.",
            },
        ]
    }
    questions = make_fixed_questions(snapshot, "en")
    assert "Built a test service." in questions[4].text
    assert questions[4].fact_ids == ("fact-abc",)
    assert "improving delivery quality" in questions[8].text
    assert questions[8].source_ids == ("research-official",)


def test_role_matched_facts_are_selected_before_unrelated_profile_facts(snapshot):
    snapshot["inputs"]["candidate"]["facts"].insert(
        0,
        {
            "fact_id": "fact-unrelated",
            "statement": "Organized a music event.",
            "confidence": "confirmed",
            "sensitive": False,
        },
    )
    snapshot["inputs"]["match_analysis"] = {
        "matches": [{"requirement_id": "req-abc", "status": "match", "fact_ids": ["fact-abc"]}]
    }
    questions = make_fixed_questions(snapshot, "en")
    assert "Built a test service." in questions[4].text
    assert questions[4].fact_ids == ("fact-abc",)


def test_prepared_question_is_used_with_its_evidence_in_english(snapshot):
    snapshot["inputs"]["answer_plans"] = {
        "questions": [
            {
                "question_id": "q-prepared",
                "category": "portfolio",
                "question": "How did you build the test service?",
                "fact_ids": ["fact-abc"],
                "requirement_ids": ["req-abc"],
            },
        ]
    }
    english = make_fixed_questions(snapshot, "en")
    assert english[4].text == "How did you build the test service?"
    assert english[4].source_question_id == "q-prepared"
    assert english[4].fact_ids == ("fact-abc",)
    assert make_fixed_questions(snapshot, "ja")[4].source_question_id is None


def test_replay_and_history_are_distinct(tmp_path, snapshot):
    store = Store(tmp_path / "bank.sqlite")
    questions = make_fixed_questions(snapshot, "en")
    first = store.create_run("example/engineer", "en", snapshot, questions)
    second = store.create_run("example/engineer", "en", snapshot, questions)
    store.present(first, 1)
    store.present(first, 1)
    store.present(second, 1)
    store.acknowledge_presentation(first, 1, f"{first}-q01")
    before = store.submit(first, 1, "one", "An answer")
    after = store.submit(first, 1, "one", "An answer")
    assert before["submission_id"] == after["submission_id"]
    with pytest.raises(ValueError, match="reused"):
        store.submit(first, 1, "one", "Changed answer")
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM question_versions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM question_concepts").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM presentations").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    reopened = Store(tmp_path / "bank.sqlite")
    assert reopened.get_run(first)["answers"][0]["text"] == "An answer"


def test_evaluation_requires_exact_answer_quote_and_known_facts():
    good = {
        "scores": {key: 3 for key in ("relevance", "specificity", "reasoning", "clarity", "reflection")},
        "quote": "I built it",
        "strength": "Specific",
        "improvement": "Explain result",
        "reason": "Shows ownership",
        "fact_ids": ["fact-abc"],
    }
    result = validate_evaluation(good, "I built it with a team", {"fact-abc"}, "portfolio")
    assert result["score"] == 75.0
    with pytest.raises(ValueError, match="quote"):
        validate_evaluation(
            {**good, "quote": "I created a billion dollars"}, "I built it", {"fact-abc"}, "portfolio"
        )
    with pytest.raises(ValueError, match="unknown"):
        validate_evaluation({**good, "fact_ids": ["fact-fake"]}, "I built it", {"fact-abc"}, "portfolio")
    with pytest.raises(ValueError, match="Japanese"):
        validate_evaluation(good, "I built it", {"fact-abc"}, "portfolio", "ja")


def test_traditional_chinese_feedback_is_normalized():
    raw = {
        "scores": {key: 3 for key in ("relevance", "specificity", "reasoning", "clarity", "reflection")},
        "quote": "我改進了流程",
        "strength": "回答清晰",
        "improvement": "需要优先说明结果",
        "reason": "证据具体",
        "fact_ids": [],
    }
    result = validate_evaluation(raw, "我改進了流程", set(), "role", "zh-Hant")
    assert "優先" in result["improvement"]
    assert "證據" in result["reason"]


def test_coached_example_uses_only_exact_confirmed_fact_text():
    raw = {
        "fact_ids": ["fact-abc"],
        "why_it_works": "Concrete",
        "outline": "Action and result",
        "next_action": "Verify the result",
        "example": "I increased revenue by 900 percent",
    }
    question = {"locale": "en", "category": "portfolio"}
    result = validate_coaching(raw, {"fact-abc": "Built a test service."}, question)
    assert "Built a test service." in result["example"]
    assert "900" not in result["example"]
    assert "[add a verified result]" in result["example"]


def test_report_with_unavailable_assessment_is_provisional(tmp_path, snapshot):
    store = Store(tmp_path / "bank.sqlite")
    run_id = store.create_run("example/engineer", "en", snapshot, make_fixed_questions(snapshot, "en"))
    for ordinal in range(1, 11):
        store.present(run_id, ordinal)
        store.acknowledge_presentation(run_id, ordinal, f"{run_id}-q{ordinal:02d}")
        store.submit(run_id, ordinal, f"submission-{ordinal}", f"Answer {ordinal}")
    store.save_evaluation(run_id, 1, {"unavailable": "model unavailable"})
    report = render_report(store.get_run(run_id))
    assert "provisional: 0/10 assessed" in report
    assert "Assessment unavailable" in report
    assert report.count("## ") == 10


def test_unavailable_assessment_can_retry_but_validated_score_is_frozen(tmp_path, snapshot):
    store = Store(tmp_path / "bank.sqlite")
    run_id = store.create_run("example/engineer", "en", snapshot, make_fixed_questions(snapshot, "en"))
    store.present(run_id, 1)
    store.acknowledge_presentation(run_id, 1, f"{run_id}-q01")
    store.submit(run_id, 1, "one", "Answer")
    store.save_evaluation(run_id, 1, {"unavailable": "first attempt failed"})
    store.save_evaluation(run_id, 1, {"score": 42.0})
    with pytest.raises(ValueError, match="cannot be revised"):
        store.save_evaluation(run_id, 1, {"score": 99.0})
    store.save_evaluation(run_id, 1, {"score": 42.0, "coaching": {"example": "Answer"}})
    assert store.get_run(run_id)["evaluations"][1]["coaching"]["example"] == "Answer"
    assert store.get_run(run_id)["evaluations"][1]["score"] == 42.0
    profile = store.practice_profile("example/engineer", "en")
    assert profile["categories"]["personal"]["average"] == 42.0
    assert profile["runs"] == 1


def test_voice_answer_preserves_raw_and_confirmed_transcripts(tmp_path, snapshot):
    store = Store(tmp_path / "bank.sqlite")
    run_id = store.create_run("example/engineer", "en", snapshot, make_fixed_questions(snapshot, "en"))
    presented = store.present(run_id, 1)
    store.acknowledge_presentation(run_id, 1, presented["event_id"])
    store.submit(
        run_id, 1, "voice-one", "I built a test service.", "voice", False, "I billed a test service."
    )
    saved = store.get_run(run_id)["answers"][0]
    assert saved["text"] == "I built a test service."
    assert saved["raw_transcript"] == "I billed a test service."
    assert "Original speech recognition" in render_report(store.get_run(run_id))


def test_sensitive_and_unreviewed_facts_never_shape_questions(snapshot):
    snapshot["inputs"]["candidate"]["facts"].extend(
        [
            {
                "fact_id": "private",
                "statement": "Private medical detail",
                "confidence": "confirmed",
                "sensitive": True,
            },
            {
                "fact_id": "draft",
                "statement": "Unverified achievement",
                "confidence": "needs-review",
                "sensitive": False,
            },
        ]
    )
    questions = make_fixed_questions(snapshot, "en")
    assert all(set(q.fact_ids) <= {"fact-abc"} for q in questions)
    assert all("Private medical" not in q.text and "Unverified" not in q.text for q in questions)


def test_role_question_binds_requirement_it_actually_asks(snapshot):
    snapshot["inputs"]["requirements"]["requirements"].insert(
        0, {"requirement_id": "low", "statement": "Unrelated low priority", "priority": "low"}
    )
    question = make_fixed_questions(snapshot, "en")[6]
    assert "Python delivery" in question.text
    assert question.requirement_ids == ("req-abc",)
