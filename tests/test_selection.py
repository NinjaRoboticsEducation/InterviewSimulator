from __future__ import annotations

import asyncio
from dataclasses import replace

from test_interview_flow import make_engine

from interview_simulator.questions import make_fixed_questions


def test_adaptive_question_comes_from_current_evidence_bank_and_survives_replay(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        snapshot = engine.wiki.snapshot("example/engineer")
        questions = make_fixed_questions(snapshot, "en")
        questions[1] = replace(
            questions[1], text="Tell me about your Python migration project and what you learned."
        )
        prior = engine.store.create_run("example/engineer", "en", snapshot, questions)
        first = engine.store.present(prior, 1)
        engine.store.acknowledge_presentation(prior, 1, first["event_id"])
        engine.store.submit(prior, 1, "prior-one", "I led a Python migration project.")
        engine.store.present(prior, 2)
        with engine.store.connect() as db:
            db.execute("UPDATE runs SET status='answered' WHERE run_id=?", (prior,))

        current = await engine.start("example/engineer", "en", flow_mode="adaptive")
        run_id = current["run_id"]
        engine.store.acknowledge_presentation(run_id, 1, current["question"]["event_id"])
        next_turn = await engine.submit(run_id, 1, "I worked on a Python migration project.", "current-one")
        assert "Python migration project" in next_turn["question"]["text"]
        run = engine.store.get_run(run_id)
        assert run["selection_decisions"][2]["policy_version"] == "bounded-bank-v1"
        assert run["selection_decisions"][2]["candidate_count"] >= 2
        replay = await engine.state(run_id)
        assert replay["question"]["event_id"] == next_turn["question"]["event_id"]
        assert len(engine.store.get_run(run_id)["selection_decisions"]) == 1
        state = replay
        for ordinal in range(2, 11):
            engine.store.acknowledge_presentation(run_id, ordinal, state["question"]["event_id"])
            state = await engine.submit(run_id, ordinal, f"Answer {ordinal}", f"adaptive-{ordinal}")
        assert state["status"] == "answered"
        assert len(engine.store.get_run(run_id)["answers"]) == 10
        assert len(engine.store.get_run(run_id)["selection_decisions"]) == 9

    asyncio.run(exercise())
