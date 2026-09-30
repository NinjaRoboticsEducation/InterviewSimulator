from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import yaml

from interviewwiki.config import Config
from interviewwiki.errors import ConfigurationError, InterviewWikiError, ValidationFailure
from interviewwiki.opportunity import register_research
from interviewwiki.resume import render_resume
from interviewwiki.service import InterviewWikiService
from interviewwiki.util import sha256_file, write_json


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_prepare_is_local_and_never_mutates_personal_wiki(project: Path) -> None:
    service = InterviewWikiService(project)
    service.initialize()
    reference = service.opportunity_create("Privacy Example", "Data Engineer")
    source = project / "JobDescriptions/privacy-example/data-engineer/sources/job.txt"
    source.write_text("A sufficiently detailed role description for a data engineer.", encoding="utf-8")
    before = tree_hashes(project / "PersonalWiki")

    prepared = service.run_prepare(reference)

    assert prepared["candidate_facts"] == 2
    assert tree_hashes(project / "PersonalWiki") == before
    assert (project / ".interviewwiki/candidate-facts.json").is_file()
    assert not any((project / "PersonalWiki").rglob("candidate-facts.json"))


def test_candidate_index_rejects_changed_registered_source(project: Path) -> None:
    service = InterviewWikiService(project)
    source = project / "PersonalWiki/raw/notes/candidate-source.md"
    source.write_text("The user-edited source no longer matches its registered hash.\n", encoding="utf-8")

    with pytest.raises(InterviewWikiError, match="source changed after registration"):
        service.candidate_build()


def test_candidate_migration_is_automatic_reviewable_and_personalwiki_read_only(project: Path) -> None:
    service = InterviewWikiService(project)
    before = tree_hashes(project / "PersonalWiki")

    result = service.candidate_migrate()

    assert tree_hashes(project / "PersonalWiki") == before
    assert result["diff"]["added"] == ["fact-delivery-improvement", "fact-python-tooling"]
    assert (project / result["walkthrough"]).is_file()
    assert service.candidate_status()["current"] is True


def test_register_existing_opportunity_folder_without_metadata(project: Path) -> None:
    service = InterviewWikiService(project)
    source = project / "JobDescriptions/example-company/product-lead/sources/JobDescription.md"
    source.parent.mkdir(parents=True)
    source.write_text("A complete Product Lead description with strategy and delivery responsibilities.\n", encoding="utf-8")

    result = service.opportunity_register("example-company/product-lead")

    assert result["reference"] == "example-company/product-lead"
    assert result["created"] is True
    assert (source.parents[1] / "opportunity.yaml").is_file()
    assert result["ingestion"]["sources"]


def test_opportunity_ingest_rejects_source_symlink(project: Path) -> None:
    service = InterviewWikiService(project)
    reference = service.opportunity_create("Boundary Example", "Designer")
    outside = project / "private-candidate-note.md"
    outside.write_text("Private local content that must never become opportunity evidence.\n", encoding="utf-8")
    source = project / f"JobDescriptions/{reference}/sources/leak.md"
    source.symlink_to(outside)

    with pytest.raises(InterviewWikiError, match="Symlinks"):
        service.opportunity_ingest(reference)


def test_focused_compatibility_prepare_creates_no_resume_or_qa_placeholders(project: Path) -> None:
    service = InterviewWikiService(project)
    reference = service.opportunity_create("Focused Example", "Researcher")
    source = project / f"JobDescriptions/{reference}/sources/job.md"
    source.write_text("A detailed researcher role requiring evidence synthesis and communication.\n", encoding="utf-8")

    service.run_prepare(reference, "compatibility-review")
    output = project / f"Output/{reference}"

    assert (output / "Evidence/requirements.json").is_file()
    assert (output / "Evidence/match-analysis.json").is_file()
    assert (output / "Interview/candidate-analysis.md").is_file()
    assert not (output / "Evidence/answer-plans.json").exists()
    assert not (output / "Evidence/resume-content.json").exists()
    assert not (output / "Interview/interview-q-and-a.md").exists()


def test_legacy_resume_upgrade_is_recoverable_and_personalwiki_read_only(project: Path) -> None:
    service = InterviewWikiService(project)
    reference = service.opportunity_create("Legacy Example", "Designer")
    evidence = project / f"Output/{reference}/Evidence"
    before = tree_hashes(project / "PersonalWiki")

    def locale(ja: bool) -> dict:
        words = ["設計", "技術", "ツール"] if ja else ["Design", "Technical", "Tools"]
        return {
            "name": "架空候補者" if ja else "Fictional Candidate",
            "headline": "デザイナー" if ja else "Designer",
            "summary": {"block_id": "summary", "text": "Pythonを使用。" if ja else "Uses Python.", "fact_ids": ["fact-python-tooling"]},
            "sections": [
                {"section_id": "experience", "title": "Experience", "placement": "main", "items": [{
                    "block_id": "exp-example", "heading": "リード" if ja else "Lead", "subheading": "架空会社" if ja else "Example Company",
                    "period": "現在" if ja else "Present", "body": "", "fact_ids": ["fact-delivery-improvement"],
                    "bullets": [{"text": "25パーセント改善。" if ja else "Improved by 25 percent.", "fact_ids": ["fact-delivery-improvement"]}],
                }]},
                {"section_id": "skills", "title": "Skills", "placement": "sidebar", "items": [
                    {"block_id": f"skill-{index}", "heading": word, "body": "", "fact_ids": ["fact-python-tooling"],
                     "bullets": [{"text": word, "fact_ids": ["fact-python-tooling"]}]}
                    for index, word in enumerate(words, 1)
                ]},
                {"section_id": "languages", "title": "Languages", "placement": "sidebar", "items": [{
                    "block_id": "languages", "heading": "言語" if ja else "Languages", "body": "", "fact_ids": ["fact-python-tooling"],
                    "bullets": [{"text": "英語 — 業務レベル" if ja else "English — Professional", "fact_ids": ["fact-python-tooling"]}],
                }]},
                {"section_id": "education", "title": "Education", "placement": "sidebar", "items": [{
                    "block_id": "education", "heading": "架空大学" if ja else "Example University", "subheading": "工学" if ja else "Engineering",
                    "period": "", "body": "", "fact_ids": ["fact-python-tooling"], "bullets": [],
                }]},
            ],
        }

    write_json(evidence / "resume-content.json", {
        "schema_version": 1, "opportunity": reference,
        "candidate": {"email": "candidate@example.test", "phone": "", "website": "", "location": ""},
        "locales": {"en": locale(False), "ja": locale(True)},
    })
    write_json(evidence / "claim-ledger.json", {"schema_version": 1, "opportunity": reference, "claims": []})
    legacy_html = project / f"Output/{reference}/Resume/index.html"
    legacy_html.write_text("<html>legacy</html>\n", encoding="utf-8")

    result = service.resume_upgrade(reference)
    converted = json.loads((evidence / "resume-content.json").read_text(encoding="utf-8"))

    assert result["upgraded"] is True
    assert converted["schema_version"] == 2
    assert converted["template_id"] == "method-v1"
    assert len(converted["locales"]["en"]["signals"]) == 4
    assert len(converted["locales"]["en"]["expertise"]) == 4
    assert (project / result["backup"] / "resume-content.json").is_file()
    assert (project / result["backup"] / "Resume/index.html").is_file()
    assert not legacy_html.exists()
    assert tree_hashes(project / "PersonalWiki") == before


def test_research_registration_requires_local_opportunity_snapshot(project: Path) -> None:
    service = InterviewWikiService(project)
    reference = service.opportunity_create("Research Example", "Analyst")
    opportunity = project / "JobDescriptions/research-example/analyst"
    snapshot = opportunity / "sources/company-page.md"
    snapshot.write_text("Public company research snapshot.\n", encoding="utf-8")

    record = register_research(
        Config.load(project),
        reference,
        source_id="research-company-page",
        url="https://example.test/company",
        title="Company page",
        publisher="Example Company",
        snapshot="sources/company-page.md",
        source_tier="official",
    )

    assert record["snapshot"] == "sources/company-page.md"
    with pytest.raises(InterviewWikiError, match="sources folder"):
        register_research(
            Config.load(project),
            reference,
            source_id="research-outside",
            url="https://example.test/outside",
            title="Outside",
            publisher="Example",
            snapshot="opportunity.yaml",
            source_tier="official",
        )


def test_valid_strict_run_and_offline_bilingual_resume(prepared: tuple[Path, InterviewWikiService, str]) -> None:
    project, service, reference = prepared

    rendered = service.resume_render(reference)
    service.manifest_finalize(reference)
    report = service.run_validate(reference, strict=True)

    assert report["valid"] is True
    html = (project / rendered["html"]).read_text(encoding="utf-8")
    assert 'id="resume-en"' in html
    assert 'id="resume-ja"' in html
    assert 'data-section-id="self-introduction"' in html
    assert 'data-section-id="personal-expertise"' in html
    assert "https://" not in html
    assert "http://" not in html
    assert html.index('<aside class="sidebar">') < html.index('<main class="main">')
    assert not any(issue["code"] == "manifest-output-stale" for issue in report["issues"])


def test_canonical_profile_photo_is_copied_and_embedded_in_both_locales(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, _service, reference = prepared
    photo = project / "PersonalWiki/raw/media/Profile.png"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))

    rendered = render_resume(Config.load(project), reference)
    html = (project / rendered["html"]).read_text(encoding="utf-8")
    copied = project / f"Output/{reference}/Resume/assets/profile.png"

    assert html.count('src="assets/profile.png"') == 2
    assert copied.is_file()
    assert sha256_file(copied) == sha256_file(photo)


def test_print_contract_places_expertise_before_page_three_self_pr(project: Path) -> None:
    css = (project / "templates/resume/method-v1/styles.css.tpl").read_text(encoding="utf-8")

    assert '#resume-en [data-section-id="self-pr"]' in css
    assert '#resume-ja [data-section-id="self-pr"]' in css
    assert '#resume-en [data-section-id="personal-expertise"]' not in css
    assert '#resume-ja [data-section-id="personal-expertise"]' not in css


def test_validation_rejects_unknown_facts_and_bilingual_drift(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    path = project / f"Output/{reference}/Evidence/resume-content.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    content["locales"]["ja"]["self_introduction"][0]["fact_ids"] = ["fact-does-not-exist"]
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = service.run_validate(reference, strict=False)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["valid"] is False
    assert "unknown-fact" in codes
    assert "bilingual-fact-parity" in codes
    with pytest.raises(ValidationFailure):
        service.resume_render(reference)


def test_validation_rejects_unledgered_unsupported_numbers(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    path = project / f"Output/{reference}/Evidence/resume-content.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    content["locales"]["en"]["professional_experience"][0]["achievements"][0]["text"] = (
        "Invented a 99 percent improvement."
    )
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = service.run_validate(reference, strict=False)

    assert report["valid"] is False
    assert any(issue["code"] == "unsupported-number" for issue in report["issues"])


def test_strict_validation_requires_two_or_three_experience_bullets(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    path = project / f"Output/{reference}/Evidence/resume-content.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    for locale in content["locales"].values():
        locale["professional_experience"][0]["responsibilities"] = (
            locale["professional_experience"][0]["responsibilities"][:1]
        )
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = service.run_validate(reference, strict=True)

    assert report["valid"] is False
    assert any(issue["code"] == "experience-bullet-count" for issue in report["issues"])


def test_strict_validation_rejects_duplicate_experience_bullets(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    path = project / f"Output/{reference}/Evidence/resume-content.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    for locale in content["locales"].values():
        bullets = locale["professional_experience"][0]["responsibilities"]
        bullets[1]["text"] = bullets[0]["text"]
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = service.run_validate(reference, strict=True)

    assert report["valid"] is False
    assert any(issue["code"] == "duplicate-experience-bullet" for issue in report["issues"])


def test_strict_validation_requires_concrete_self_pr_case_evidence(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    path = project / f"Output/{reference}/Evidence/resume-content.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    for locale in content["locales"].values():
        for paragraph in locale["self_pr"]:
            paragraph["fact_ids"] = ["fact-python-tooling"]
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = service.run_validate(reference, strict=True)

    assert report["valid"] is False
    codes = {issue["code"] for issue in report["issues"]}
    assert "self-pr-evidence-breadth" in codes
    assert "self-pr-case-grounding" in codes


def test_validation_detects_opportunity_source_changed_after_ingestion(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    source = project / f"JobDescriptions/{reference}/sources/job.md"
    source.write_text("The job source changed after the evidence snapshot.\n", encoding="utf-8")

    report = service.run_validate(reference, strict=False)

    assert report["valid"] is False
    assert any(issue["code"] == "opportunity-source-changed" for issue in report["issues"])


def test_strict_validation_rejects_output_added_after_finalization(
    prepared: tuple[Path, InterviewWikiService, str]
) -> None:
    project, service, reference = prepared
    service.resume_render(reference)
    service.manifest_finalize(reference)
    (project / f"Output/{reference}/Reports/unlisted.md").write_text("late output\n", encoding="utf-8")

    report = service.run_validate(reference, strict=True)

    assert report["valid"] is False
    assert any(issue["code"] == "manifest-output-unlisted" for issue in report["issues"])


def test_config_rejects_absolute_paths(project: Path) -> None:
    path = project / "interviewwiki.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["paths"]["output"] = "/tmp/not-portable"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="project-relative"):
        Config.load(project)
