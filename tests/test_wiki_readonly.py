from __future__ import annotations

from pathlib import Path

from interviewwiki.artifacts import iter_preparation_artifacts

from interview_simulator.wiki import WikiAdapter


def test_preflight_without_local_wiki_environment_does_not_write(tmp_path: Path):
    root = tmp_path / "sim"
    wiki = root / "InterviewWiki"
    wiki.mkdir(parents=True)
    (wiki / "interviewwiki.yaml").write_text(
        "version: 1\npaths:\n  job_descriptions: JobDescriptions\n  personal_wiki: PersonalWiki\n"
        "  output: Output\n  runtime: .interviewwiki\n  resume_template: templates/resume/method-v1\n",
        encoding="utf-8",
    )
    personal = wiki / "PersonalWiki"
    personal.mkdir()
    (personal / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    opportunity = wiki / "JobDescriptions/acme/engineer"
    opportunity.mkdir(parents=True)
    (opportunity / "opportunity.yaml").write_text(
        "version: 1\ncompany: Acme\ncompany_slug: acme\nrole: Engineer\n"
        "opportunity_slug: engineer\nstatus: registered\n",
        encoding="utf-8",
    )
    before = sorted(str(path.relative_to(wiki)) for path in wiki.rglob("*") if path.is_file())
    job = WikiAdapter(wiki).inspect("acme/engineer")
    after = sorted(str(path.relative_to(wiki)) for path in wiki.rglob("*") if path.is_file())
    assert not job.ready
    assert any("PersonalWiki" in reason for reason in job.reasons)
    assert before == after


def test_package_artifact_inventory_excludes_only_simulations(tmp_path: Path):
    output = tmp_path / "Output"
    (output / "Reports").mkdir(parents=True)
    (output / "Evidence").mkdir()
    (output / "Simulations/run-a").mkdir(parents=True)
    (output / "Reports/run-manifest.json").write_text("{}")
    (output / "Simulations/run-a/report.md").write_text("report")
    (output / "Evidence/requirements.json").write_text("{}")
    (output / "Evidence/unexpected.txt").write_text("unexpected")
    actual = {item.relative_to(output).as_posix() for item in iter_preparation_artifacts(output)}
    assert actual == {"Evidence/requirements.json", "Evidence/unexpected.txt"}
