from __future__ import annotations

import asyncio
import json
from pathlib import Path

from interview_simulator.adk_runtime import InterviewFlow
from interview_simulator.config import Settings
from interview_simulator.engine import InterviewEngine
from interview_simulator.storage import Store


class FakeWiki:
    def __init__(self, root: Path):
        self.root = root

    def snapshot(self, reference: str):
        assert reference == "example/engineer"
        return {
            "reference": reference,
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

    def simulation_dir(self, reference: str, run_id: str) -> Path:
        assert reference == "example/engineer"
        return self.root / "Simulations" / run_id


def make_engine(root: Path) -> InterviewEngine:
    settings = Settings(root, root / "InterviewWiki", root / ".simulator")
    engine = object.__new__(InterviewEngine)
    engine.settings = settings
    engine.wiki = FakeWiki(root)
    engine.store = Store(settings.state_root / "question-bank.sqlite")
    engine.flow = InterviewFlow(settings)
    engine.adk = None
    return engine


def test_ten_adk_pauses_resume_after_restart_and_saved_answer_replay(tmp_path):
    async def exercise():
        engine = make_engine(tmp_path)
        state = await engine.start("example/engineer", "en")
        run_id = state["run_id"]
        for ordinal in range(1, 11):
            assert state["question"]["ordinal"] == ordinal
            engine.store.acknowledge_presentation(run_id, ordinal, state["question"]["event_id"])
            if ordinal == 4:
                # Process dies after the answer transaction, before ADK resume.
                engine.store.submit(run_id, ordinal, f"submission-{ordinal}", f"Answer {ordinal}")
                engine = make_engine(tmp_path)
                state = await engine.state(run_id)
            else:
                state = await engine.submit(run_id, ordinal, f"Answer {ordinal}", f"submission-{ordinal}")
        assert state["status"] == "answered"
        assert state["question"] is None
        assert len(engine.store.get_run(run_id)["answers"]) == 10
        assert (tmp_path / ".simulator/adk-sessions.sqlite").is_file()

    asyncio.run(exercise())


def test_complete_report_preserves_scores_and_creates_new_job_run(tmp_path):
    class StubAssessor:
        async def evaluate(self, question, answer, facts, requirement):
            return {
                "scores": {
                    key: 3 for key in ("relevance", "specificity", "reasoning", "clarity", "reflection")
                },
                "quote": answer,
                "strength": "A concrete answer.",
                "improvement": "Add a verified result.",
                "reason": "Relevant but lacks a result.",
                "fact_ids": [],
                "score": 75.0,
            }

        async def coach(self, question, answer, facts, assessment):
            return {
                "fact_ids": list(facts),
                "example": "Built a test service. [Add a verified result.]",
                "why_it_works": "Shows relevant work.",
                "outline": "Action, result, reflection.",
                "next_action": "Practice with one verified metric.",
            }

    async def exercise():
        engine = make_engine(tmp_path)
        engine.adk = StubAssessor()
        state = await engine.start("example/engineer", "en")
        run_id = state["run_id"]
        for ordinal in range(1, 11):
            engine.store.acknowledge_presentation(run_id, ordinal, state["question"]["event_id"])
            state = await engine.submit(run_id, ordinal, f"Answer {ordinal}", f"submission-{ordinal}")
        path = await engine.evaluate(run_id)
        report = path.read_text(encoding="utf-8")
        assert "75.0/100" in report
        assert report.count("**Example answer:**") == 10
        assert sum(line.startswith("## ") for line in report.splitlines()) == 11
        assert all(f"## {ordinal}." in report for ordinal in range(1, 11))
        manifest = json.loads((path.parent / "simulation-manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "complete"
        another = await engine.start("example/engineer", "en")
        assert another["run_id"] != run_id
        assert path.is_file()

    asyncio.run(exercise())
