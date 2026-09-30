from __future__ import annotations

import asyncio
import zipfile

import pytest
from test_interview_flow import FakeWiki, make_engine

from interview_simulator.config import Settings
from interview_simulator.portability import delete_run, export_state, import_state


def test_verified_backup_restore_and_selective_delete(monkeypatch, tmp_path):
    monkeypatch.setattr("interview_simulator.portability.WikiAdapter", lambda path: FakeWiki(path.parent))
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    engine = make_engine(source)

    async def prepare():
        state = await engine.start("example/engineer", "en")
        engine.store.acknowledge_presentation(state["run_id"], 1, state["question"]["event_id"])
        await engine.submit(state["run_id"], 1, "I built a test service", "one")
        return state["run_id"]

    run_id = asyncio.run(prepare())
    archive = tmp_path / "private-backup.zip"
    export_state(engine.settings, archive)
    assert archive.is_file()
    with pytest.raises(FileExistsError):
        export_state(engine.settings, archive)
    target_settings = Settings(target, target / "InterviewWiki", target / ".simulator")
    import_state(target_settings, archive)
    restored = make_engine(target)
    assert restored.store.get_run(run_id)["answers"][0]["text"] == "I built a test service"
    assert asyncio.run(restored.state(run_id))["question"]["ordinal"] == 2
    with pytest.raises(ValueError, match="empty"):
        import_state(target_settings, archive)
    delete_run(target_settings, run_id)
    with pytest.raises(KeyError):
        restored.store.get_run(run_id)
    assert not (target / "Simulations" / run_id).exists()


def test_archive_rejects_traversal_before_writing(monkeypatch, tmp_path):
    monkeypatch.setattr("interview_simulator.portability.WikiAdapter", lambda path: FakeWiki(path.parent))
    target = tmp_path / "target"
    target.mkdir()
    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("manifest.json", '{"format":1,"files":{"../outside":"sha256:bad"},"runs":[]}')
        file.writestr("../outside", "bad")
    with pytest.raises(ValueError, match="Unsafe"):
        import_state(Settings(target, target / "InterviewWiki", target / ".simulator"), archive)
    assert not (tmp_path / "outside").exists()


def test_report_manifest_verifies_and_detects_tampering(monkeypatch, tmp_path):
    from interview_simulator.portability import verify_run

    engine = make_engine(tmp_path)
    monkeypatch.setattr("interview_simulator.portability.WikiAdapter", lambda path: FakeWiki(path.parent))

    class Assessor:
        async def evaluate(self, question, answer, facts, requirement):
            return {
                "score": 75.0,
                "scores": {
                    key: 3 for key in ("relevance", "specificity", "reasoning", "clarity", "reflection")
                },
                "quote": answer,
                "strength": "Clear",
                "improvement": "Add a result",
                "reason": "Relevant",
                "fact_ids": [],
            }

        async def coach(self, question, answer, facts, assessment):
            return {
                "example": "Verified example",
                "why_it_works": "Grounded",
                "outline": "Context, action, result",
                "next_action": "Practise",
                "fact_ids": [],
            }

    engine.adk = Assessor()

    async def exercise():
        state = await engine.start("example/engineer", "en")
        for ordinal in range(1, 11):
            engine.store.acknowledge_presentation(state["run_id"], ordinal, state["question"]["event_id"])
            state = await engine.submit(state["run_id"], ordinal, "Answer", str(ordinal))
        return state["run_id"], await engine.evaluate(state["run_id"])

    run_id, report = asyncio.run(exercise())
    assert verify_run(engine.settings, run_id)["status"] == "complete"
    report.write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify_run(engine.settings, run_id)
