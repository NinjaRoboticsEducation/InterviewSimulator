from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from .artifacts import iter_preparation_artifacts
from .candidate import candidate_status, load_candidate_index, migrate_candidate_index
from .config import Config
from .errors import InterviewWikiError
from .opportunity import ingest_opportunity, load_opportunity
from .profile import profile_photo_status
from .util import operation_lock, read_json, sha256_file, sha256_paths, utc_now, write_json, write_text


WORKFLOW_VERSION = "0.2.1"


TASK_KINDS = {
    "full-package",
    "compatibility-review",
    "research-refresh",
    "requirements-review",
    "interview-qa",
    "portfolio-selection",
    "resume-content",
    "resume-render",
    "validation-audit",
}


def initialize_project(config: Config) -> None:
    for path in (config.job_descriptions, config.personal_wiki, config.output, config.runtime):
        path.mkdir(parents=True, exist_ok=True)


def _write_if_missing(path: Path, payload: Any) -> None:
    if not path.exists():
        write_json(path, payload)


def _candidate_for_run(config: Config) -> tuple[dict[str, Any], str | None]:
    status = candidate_status(config)
    if not status["personal_wiki"]["ready"]:
        raise InterviewWikiError("PersonalWiki strict lint must pass before preparing an interview task")
    if status["current"]:
        return load_candidate_index(config), None
    migration = migrate_candidate_index(config)
    return migration["candidate"], migration["migration_id"]


def _stable_inputs(config: Config, candidate: dict[str, Any], opportunity_sources: Path) -> dict[str, str]:
    photo = profile_photo_status(config)
    if not photo["valid"]:
        raise InterviewWikiError(str(photo.get("error") or "Profile photo is invalid"))
    return {
        "opportunity_sources": sha256_file(opportunity_sources),
        "candidate_facts": candidate["content_hash"],
        "profile_photo": str(photo["content_hash"]),
        "resume_template": sha256_paths(
            [path for path in config.resume_template.rglob("*") if path.is_file()], config.resume_template
        ),
    }


def _resume_shell(reference: str) -> dict[str, Any]:
    def locale(language: str) -> dict[str, Any]:
        ja = language == "ja"
        return {
            "name": "",
            "headline": "",
            "sidebar": {
                "labels": {
                    "contact": "連絡先" if ja else "Contact", "languages": "言語" if ja else "Languages",
                    "skills": "専門領域" if ja else "Skills", "tools": "ツール" if ja else "Tools",
                    "education": "学歴" if ja else "Education", "awards": "受賞歴" if ja else "Awards",
                },
                "languages": [], "skills": [], "tools": [], "education": [], "awards": [],
            },
            "section_labels": {
                "self_introduction": "自己紹介" if ja else "Self Introduction",
                "professional_experience": "職務経歴" if ja else "Professional Experience",
                "responsibilities": "担当業務" if ja else "Responsibilities",
                "achievements": "主な実績" if ja else "Key Achievements",
                "earlier_career": "その他の職務経歴" if ja else "Earlier Career",
                "earlier_headers": ["期間", "職位", "会社", "勤務地"] if ja else ["Period", "Title", "Company", "Location"],
                "expertise": "個人の専門領域" if ja else "Personal Expertise",
                "self_pr": "自己PR" if ja else "Self PR",
            },
            "self_introduction": [], "signals": [], "professional_experience": [],
            "earlier_career": [], "expertise": [], "self_pr": [],
        }
    return {
        "schema_version": 2, "template_id": "method-v1", "opportunity": reference,
        "candidate": {"email": "", "phone": "", "website": "", "location": "", "consent_to_publish": True},
        "locales": {"en": locale("en"), "ja": locale("ja")},
    }


def prepare_run(config: Config, reference: str, task_kind: str = "full-package") -> dict[str, Any]:
    if task_kind not in TASK_KINDS:
        raise InterviewWikiError(f"Unknown task kind: {task_kind}")
    parsed, _ = load_opportunity(config, reference)
    lock = config.runtime / "locks" / f"prepare-{'-'.join(parsed)}.lock"
    with operation_lock(lock):
        sources = ingest_opportunity(config, reference)
        candidate, migration_id = _candidate_for_run(config)
        output = config.opportunity_output(parsed)
        evidence = output / "Evidence"
        reports = output / "Reports"
        interview = output / "Interview"
        resume = output / "Resume"
        for path in (evidence, reports, interview, resume / "assets"):
            path.mkdir(parents=True, exist_ok=True)

        needs = {
            "full-package": {"requirements", "match", "answers", "resume", "ledger", "analysis", "qa"},
            "compatibility-review": {"requirements", "match", "analysis"},
            "research-refresh": set(),
            "requirements-review": {"requirements"},
            "interview-qa": {"requirements", "match", "answers", "ledger", "qa"},
            "portfolio-selection": {"requirements", "match", "analysis"},
            "resume-content": {"requirements", "match", "resume", "ledger"},
            "resume-render": {"resume", "ledger"},
            "validation-audit": set(),
        }[task_kind]
        if "requirements" in needs:
            _write_if_missing(evidence / "requirements.json", {"schema_version": 1, "opportunity": reference, "requirements": [], "source_coverage": []})
        if "match" in needs:
            _write_if_missing(evidence / "match-analysis.json", {"schema_version": 1, "opportunity": reference, "matches": [], "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}, "recruiter_concerns": [], "preparation_strategy": []})
        if "answers" in needs:
            _write_if_missing(evidence / "answer-plans.json", {"schema_version": 1, "opportunity": reference, "questions": []})
        if "resume" in needs:
            _write_if_missing(evidence / "resume-content.json", _resume_shell(reference))
        if "ledger" in needs:
            _write_if_missing(evidence / "claim-ledger.json", {"schema_version": 1, "opportunity": reference, "claims": []})
        _write_if_missing(evidence / "research-sources.json", {"schema_version": 1, "opportunity": reference, "sources": []})
        if "analysis" in needs and not (interview / "candidate-analysis.md").exists():
            write_text(interview / "candidate-analysis.md", "# Candidate Experience & Compatibility Audit\n\nGeneration pending.\n")
        if "qa" in needs and not (interview / "interview-q-and-a.md").exists():
            write_text(interview / "interview-q-and-a.md", "# Interview Q&A\n\nGeneration pending.\n")

        execution_id = uuid.uuid4().hex
        manifest = {
            "schema_version": 2, "opportunity": reference, "workflow_version": WORKFLOW_VERSION,
            "task_kind": task_kind, "execution_id": execution_id, "created_at": utc_now(),
            "tool": os.environ.get("INTERVIEWWIKI_AGENT_TOOL", "interviewwiki"),
            "model": os.environ.get("INTERVIEWWIKI_AGENT_MODEL", "unknown"),
            "candidate_migration_id": migration_id,
            "inputs": _stable_inputs(config, candidate, evidence / "opportunity-sources.json"),
            "outputs": {},
        }
        write_json(reports / "run-manifest.json", manifest)
        write_json(reports / "task-manifest.json", {"schema_version": 1, "opportunity": reference, "task_kind": task_kind, "execution_id": execution_id, "status": "prepared"})
        return {"opportunity": reference, "task_kind": task_kind, "opportunity_sources": len(sources["sources"]), "candidate_facts": len(candidate["facts"]), "candidate_migration_id": migration_id, "output": output.relative_to(config.root).as_posix()}


def finalize_manifest(config: Config, reference: str, task_kind: str | None = None) -> dict[str, Any]:
    parsed = load_opportunity(config, reference)[0]
    output = config.opportunity_output(parsed)
    path = output / "Reports/run-manifest.json"
    manifest = read_json(path)
    manifest["workflow_version"] = WORKFLOW_VERSION
    if task_kind and manifest.get("task_kind") != task_kind:
        raise InterviewWikiError("Task kind does not match the prepared run")
    candidate = load_candidate_index(config, rebuild=True)
    opportunity_sources = output / "Evidence/opportunity-sources.json"
    manifest["inputs"] = _stable_inputs(config, candidate, opportunity_sources)
    manifest["completed_at"] = utc_now()
    task_path = output / "Reports/task-manifest.json"
    if task_path.is_file():
        task = read_json(task_path)
        task["status"] = "complete"
        task["completed_at"] = manifest["completed_at"]
        write_json(task_path, task)
    files = sorted(iter_preparation_artifacts(output))
    manifest["outputs"] = {item.relative_to(output).as_posix(): sha256_file(item) for item in files}
    write_json(path, manifest)
    return manifest
