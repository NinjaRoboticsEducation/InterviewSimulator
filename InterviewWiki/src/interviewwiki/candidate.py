from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .errors import InterviewWikiError
from .frontmatter import parse_file
from .profile import accepted_profile_filenames, profile_photo_status
from .util import (
    ensure_within,
    read_json,
    reject_symlink_path,
    sha256_file,
    sha256_json,
    sha256_paths,
    utc_now,
    write_json,
    write_text,
)


FACT_ID_RE = re.compile(r"^fact-[a-z0-9][a-z0-9-]{2,119}$")
FACT_KINDS = {
    "employment",
    "responsibility",
    "achievement",
    "skill",
    "project",
    "education",
    "language",
    "award",
    "portfolio",
}


def _catalog_records(config: Config) -> dict[str, dict[str, Any]]:
    catalog = config.personal_wiki / "raw/_catalog"
    records: dict[str, dict[str, Any]] = {}
    if not catalog.exists():
        return records
    for path in sorted(catalog.glob("src-*.yaml")):
        reject_symlink_path(path, config.personal_wiki)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict) and data.get("id"):
            records[str(data["id"])] = data
    return records


def _candidate_inputs(config: Config) -> list[Path]:
    inputs: list[Path] = []
    for relative in ("llmwiki.yaml",):
        path = config.personal_wiki / relative
        if path.is_file() and not path.is_symlink():
            inputs.append(path)
    for base, pattern in ((config.personal_wiki / "wiki", "*.md"), (config.personal_wiki / "raw/_catalog", "src-*.yaml")):
        if base.is_dir():
            inputs.extend(path for path in base.rglob(pattern) if path.is_file() and not path.is_symlink())
    return sorted(set(inputs))


def personal_status(config: Config, *, allow_uv: bool = True) -> dict[str, Any]:
    """Run the strict PersonalWiki gate when its local application is present."""
    pyproject = config.personal_wiki / "pyproject.toml"
    if not pyproject.is_file():
        return {"ready": True, "strict_lint": "not-configured", "issues": []}
    local_cli_candidates = (
        config.personal_wiki / ".venv/bin/llmwiki",
        config.personal_wiki / ".venv/Scripts/llmwiki.exe",
    )
    local_cli = next((path for path in local_cli_candidates if path.is_file()), None)
    if local_cli:
        command = [str(local_cli), "lint", "--strict", "--format", "json"]
    else:
        if not allow_uv:
            return {
                "ready": False,
                "strict_lint": "unavailable",
                "issues": ["A local PersonalWiki llmwiki executable is required for read-only preflight"],
            }
        uv = shutil.which("uv")
        if not uv:
            return {
                "ready": False,
                "strict_lint": "unavailable",
                "issues": ["PersonalWiki has no local llmwiki executable and uv is not available"],
            }
        command = [uv, "run", "--locked", "llmwiki", "lint", "--strict", "--format", "json"]
    completed = subprocess.run(
        command,
        cwd=config.personal_wiki,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    issues: list[Any]
    try:
        import json

        if not completed.stdout.strip() and completed.returncode != 0:
            raise ValueError
        issues = json.loads(completed.stdout or "[]")
    except ValueError:
        issues = [completed.stderr.strip() or completed.stdout.strip() or "PersonalWiki lint failed"]
    accepted_photo_paths = {f"raw/media/{name}" for name in accepted_profile_filenames(config)}
    presentation_notes = [
        issue for issue in issues
        if isinstance(issue, dict)
        and issue.get("severity") == "suggestion"
        and issue.get("code") == "unregistered-source"
        and issue.get("path") in accepted_photo_paths
    ]
    blocking = [issue for issue in issues if issue not in presentation_notes]
    ready = not blocking and (completed.returncode == 0 or bool(presentation_notes))
    return {
        "ready": ready,
        "strict_lint": "passed" if ready else "failed",
        "issues": blocking,
        "notes": presentation_notes,
    }


def candidate_status(config: Config, *, allow_uv: bool = True) -> dict[str, Any]:
    source_hash = sha256_paths(_candidate_inputs(config), config.personal_wiki)
    index_path = config.runtime / "candidate-facts.json"
    current = read_json(index_path) if index_path.is_file() else {}
    return {
        "personal_wiki": personal_status(config, allow_uv=allow_uv),
        "source_fingerprint": source_hash,
        "index_exists": index_path.is_file(),
        "index_fingerprint": current.get("personal_wiki_hash"),
        "current": bool(index_path.is_file() and current.get("personal_wiki_hash") == source_hash),
        "fact_count": len(current.get("facts", [])),
        "profile_photo": profile_photo_status(config),
    }


def build_candidate_index(
    config: Config, *, require_personal_ready: bool = True, publish: bool = True
) -> dict[str, Any]:
    wiki_root = config.personal_wiki / "wiki"
    if not wiki_root.is_dir():
        raise InterviewWikiError("Configured PersonalWiki has no wiki folder")
    if require_personal_ready:
        readiness = personal_status(config)
        if not readiness["ready"]:
            raise InterviewWikiError("PersonalWiki strict lint must pass before candidate migration")
    catalog = _catalog_records(config)
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = sorted(
        path
        for path in wiki_root.rglob("*.md")
        if path.name not in {"index.md", "log.md"} and not path.is_symlink()
    )
    for page in pages:
        document = parse_file(page)
        page_facts = document.metadata.get("candidate_facts") or []
        if not isinstance(page_facts, list):
            raise InterviewWikiError(f"candidate_facts must be a list: {page}")
        page_sources = {
            str(item.get("id")): item
            for item in document.metadata.get("sources", [])
            if isinstance(item, dict) and item.get("id")
        }
        for item in page_facts:
            if not isinstance(item, dict):
                raise InterviewWikiError(f"Candidate fact must be a mapping: {page}")
            fact_id = str(item.get("fact_id", ""))
            if not FACT_ID_RE.fullmatch(fact_id):
                raise InterviewWikiError(f"Invalid candidate fact ID '{fact_id}' in {page}")
            if fact_id in seen:
                raise InterviewWikiError(f"Duplicate candidate fact ID: {fact_id}")
            seen.add(fact_id)
            kind = str(item.get("kind", ""))
            if kind not in FACT_KINDS:
                raise InterviewWikiError(f"Invalid candidate fact kind '{kind}' for {fact_id}")
            statement = str(item.get("statement", "")).strip()
            if not statement:
                raise InterviewWikiError(f"Candidate fact has no statement: {fact_id}")
            source_ids = [str(value) for value in item.get("source_ids", [])]
            if not source_ids:
                raise InterviewWikiError(f"Candidate fact has no source_ids: {fact_id}")
            evidence = []
            for source_id in source_ids:
                page_source = page_sources.get(source_id)
                record = catalog.get(source_id)
                if page_source is None or record is None:
                    raise InterviewWikiError(f"Candidate fact {fact_id} uses unknown source {source_id}")
                page_hash = str(page_source.get("content_hash", ""))
                record_hash = str(record.get("content_hash", ""))
                if not page_hash or page_hash != record_hash:
                    raise InterviewWikiError(f"Candidate fact {fact_id} uses a stale source hash")
                raw_path = Path(str(record.get("path", "")))
                if raw_path.is_absolute() or ".." in raw_path.parts:
                    raise InterviewWikiError(f"Candidate source path is not project-relative: {source_id}")
                source_path = ensure_within(config.personal_wiki / raw_path, config.personal_wiki, must_exist=True)
                reject_symlink_path(source_path, config.personal_wiki)
                if not source_path.is_file():
                    raise InterviewWikiError(f"Candidate fact {fact_id} source file is missing: {source_id}")
                if sha256_file(source_path) != record_hash:
                    raise InterviewWikiError(f"Candidate fact {fact_id} source changed after registration")
                evidence.append({"source_id": source_id, "source_hash": record_hash})
            confidence = str(item.get("confidence", "confirmed"))
            if confidence not in {"confirmed", "needs-review"}:
                raise InterviewWikiError(f"Candidate fact {fact_id} has invalid confidence: {confidence}")
            facts.append(
                {
                    "fact_id": fact_id,
                    "kind": kind,
                    "statement": statement,
                    "wiki_page": page.relative_to(config.personal_wiki).as_posix(),
                    "evidence": evidence,
                    "qualifiers": item.get("qualifiers") or {},
                    "confidence": confidence,
                    "sensitive": bool(item.get("sensitive", False)),
                }
            )
    hash_inputs = _candidate_inputs(config)
    facts = sorted(facts, key=lambda item: item["fact_id"])
    payload = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "personal_wiki_hash": sha256_paths(hash_inputs, config.personal_wiki),
        "facts": facts,
    }
    payload["content_hash"] = sha256_json({"personal_wiki_hash": payload["personal_wiki_hash"], "facts": facts})
    if publish:
        write_json(config.runtime / "candidate-facts.json", payload)
    return payload


def migrate_candidate_index(config: Config) -> dict[str, Any]:
    """Plan, validate, and publish a derived candidate index without touching PersonalWiki."""
    before_hash = sha256_paths(_candidate_inputs(config), config.personal_wiki)
    previous_path = config.runtime / "candidate-facts.json"
    previous = read_json(previous_path) if previous_path.is_file() else {"facts": []}
    migration_id = f"candidate-{uuid.uuid4().hex[:12]}"
    migration_root = config.runtime / "candidate-migrations" / migration_id
    plan = {
        "schema_version": 1,
        "migration_id": migration_id,
        "created_at": utc_now(),
        "approval_mode": "automatic-derived-state",
        "personal_wiki_hash": before_hash,
        "write_scope": [".interviewwiki"],
    }
    write_json(migration_root / "plan.json", plan)
    candidate = build_candidate_index(config, publish=False)
    write_json(migration_root / "candidate-facts.staged.json", candidate)
    after_hash = sha256_paths(_candidate_inputs(config), config.personal_wiki)
    if before_hash != after_hash:
        raise InterviewWikiError("PersonalWiki changed during candidate migration")
    write_json(config.runtime / "candidate-facts.json", candidate)
    prior = {item["fact_id"]: item for item in previous.get("facts", [])}
    current = {item["fact_id"]: item for item in candidate.get("facts", [])}
    changed = sorted(fact_id for fact_id in prior.keys() & current.keys() if prior[fact_id] != current[fact_id])
    diff = {
        "added": sorted(current.keys() - prior.keys()),
        "changed": changed,
        "retired": sorted(prior.keys() - current.keys()),
        "unchanged": len(prior.keys() & current.keys()) - len(changed),
    }
    validation = {
        "valid": True,
        "personal_wiki_unchanged": True,
        "strict_lint": "passed",
        "fact_count": len(current),
        "content_hash": candidate["content_hash"],
    }
    manifest = {
        "schema_version": 1,
        "migration_id": migration_id,
        "completed_at": utc_now(),
        "inputs": {"personal_wiki": before_hash},
        "outputs": {"candidate_facts": candidate["content_hash"]},
    }
    write_json(migration_root / "diff.json", diff)
    write_json(migration_root / "validation.json", validation)
    write_json(migration_root / "manifest.json", manifest)
    walkthrough = (
        "# Candidate Fact Migration Walkthrough\n\n"
        f"- Migration: `{migration_id}`\n"
        f"- PersonalWiki strict lint: passed\n"
        f"- PersonalWiki unchanged: yes\n"
        f"- Published facts: {len(current)}\n"
        f"- Added: {len(diff['added'])}\n"
        f"- Changed: {len(diff['changed'])}\n"
        f"- Retired: {len(diff['retired'])}\n"
        f"- Candidate content hash: `{candidate['content_hash']}`\n"
    )
    write_text(migration_root / "walkthrough.md", walkthrough)
    return {
        "migration_id": migration_id,
        "candidate": candidate,
        "diff": diff,
        "walkthrough": (migration_root / "walkthrough.md").relative_to(config.root).as_posix(),
    }


def load_candidate_index(config: Config, *, rebuild: bool = False) -> dict[str, Any]:
    path = config.runtime / "candidate-facts.json"
    if rebuild or not path.is_file():
        return build_candidate_index(config)
    from .util import read_json

    return read_json(path)


def search_candidate(config: Config, query: str, limit: int = 20) -> list[dict[str, Any]]:
    terms = {token for token in re.findall(r"[^\W_]+", query.lower()) if len(token) > 1}
    if not terms:
        return []
    results = []
    for fact in load_candidate_index(config).get("facts", []):
        text = str(fact.get("statement", "")).lower()
        tokens = set(re.findall(r"[^\W_]+", text))
        matched = terms & tokens
        if not matched:
            continue
        score = len(matched) * 10 + sum(text.count(term) for term in matched)
        results.append({**fact, "score": score})
    return sorted(results, key=lambda item: (-item["score"], item["fact_id"]))[:limit]
