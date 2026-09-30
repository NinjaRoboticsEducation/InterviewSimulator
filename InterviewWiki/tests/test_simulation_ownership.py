from __future__ import annotations

from pathlib import Path

import pytest

from interviewwiki.artifacts import iter_preparation_artifacts
from interviewwiki.service import InterviewWikiService
from interviewwiki.util import sha256_file


def test_simulation_tree_is_owned_separately(tmp_path: Path):
    output = tmp_path / "Output"
    (output / "Reports").mkdir(parents=True)
    (output / "Interview").mkdir()
    (output / "Simulations/run-a").mkdir(parents=True)
    (output / "Reports/run-manifest.json").write_text("{}")
    (output / "Simulations/run-a/report.md").write_text("report")
    (output / "Interview/qa.md").write_text("package")
    assert [item.relative_to(output).as_posix() for item in iter_preparation_artifacts(output)] == ["Interview/qa.md"]


def test_two_simulations_do_not_invalidate_finalized_package(
    prepared: tuple[Path, InterviewWikiService, str],
):
    project, service, reference = prepared
    service.resume_render(reference)
    service.manifest_finalize(reference)
    assert service.run_validate(reference, strict=True)["valid"]
    output = project / "Output" / reference
    for run_id in ("run-one", "run-two"):
        path = output / "Simulations" / run_id / "report.md"
        path.parent.mkdir(parents=True)
        path.write_text("Synthetic interview report.\n", encoding="utf-8")
    assert service.run_validate(reference, strict=True)["valid"]
    (output / "Evidence" / "unlisted.txt").write_text("wrong owner", encoding="utf-8")
    assert not service.run_validate(reference, strict=True)["valid"]


def test_simulator_snapshot_reads_valid_package_without_writes(
    prepared: tuple[Path, InterviewWikiService, str], monkeypatch: pytest.MonkeyPatch,
):
    import interview_simulator.wiki as simulator_wiki

    project, service, reference = prepared
    service.resume_render(reference)
    service.manifest_finalize(reference)
    service.run_validate(reference, strict=True)
    monkeypatch.setattr(simulator_wiki, "candidate_status", lambda config, allow_uv=False: {
        "personal_wiki": {"strict_lint": "passed"}, "current": True,
    })
    before = {path.relative_to(project).as_posix(): sha256_file(path)
              for path in project.rglob("*") if path.is_file()}
    adapter = simulator_wiki.WikiAdapter(project)
    assert adapter.inspect(reference).ready
    snapshot = adapter.snapshot(reference)
    after = {path.relative_to(project).as_posix(): sha256_file(path)
             for path in project.rglob("*") if path.is_file()}
    assert snapshot["reference"] == reference
    assert snapshot["inputs"]["candidate"]["facts"]
    assert before == after
