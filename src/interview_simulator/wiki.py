from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from interviewwiki.candidate import candidate_status
from interviewwiki.config import Config
from interviewwiki.opportunity import load_opportunity
from interviewwiki.util import parse_ref, reject_symlink_path, sha256_file
from interviewwiki.validation import validate_run

from .files import reject_links


@dataclass(frozen=True)
class Opportunity:
    reference: str
    company: str
    role: str
    ready: bool
    reasons: tuple[str, ...]


class WikiAdapter:
    """Read-only bridge to manually prepared InterviewWiki packages."""

    def __init__(self, wiki_root: Path):
        self.config = Config.load(wiki_root)

    def list_opportunities(self) -> list[Opportunity]:
        results = []
        for path in sorted(self.config.job_descriptions.glob("*/*/opportunity.yaml")):
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                continue
            ref = "/".join(path.relative_to(self.config.job_descriptions).parts[:2])
            try:
                results.append(self.inspect(ref))
            except Exception as exc:  # noqa: BLE001 - list other jobs if one package is malformed
                results.append(Opportunity(ref, ref.split("/")[0], ref.split("/")[1], False, (str(exc),)))
        return results

    def inspect(self, reference: str) -> Opportunity:
        parsed, metadata = load_opportunity(self.config, reference)
        reasons: list[str] = []
        status = candidate_status(self.config, allow_uv=False)
        if status["personal_wiki"].get("strict_lint") != "passed":
            reasons.append("PersonalWiki strict review has not passed")
        if not status["current"]:
            reasons.append("Candidate facts are missing or stale; run manual migration")
        output = self.config.opportunity_output(parsed)
        manifest_path = output / "Reports/run-manifest.json"
        if not manifest_path.is_file():
            reasons.append("Preparation package is missing")
        elif status["current"]:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("task_kind") != "full-package" or not manifest.get("completed_at"):
                reasons.append("Complete the full interview package first")
            report = validate_run(
                self.config, reference, strict=True, task_kind="full-package", write_report=False
            )
            reasons.extend(
                str(issue["message"]) for issue in report["issues"] if issue["severity"] == "error"
            )
        return Opportunity(
            reference,
            str(metadata.get("company", parsed[0])),
            str(metadata.get("role", parsed[1])),
            not reasons,
            tuple(reasons),
        )

    def snapshot(self, reference: str) -> dict[str, Any]:
        readiness = self.inspect(reference)
        if not readiness.ready:
            raise ValueError("Opportunity is not ready: " + "; ".join(readiness.reasons))
        ref = parse_ref(reference)
        output = self.config.opportunity_output(ref)
        paths = {
            "candidate": self.config.runtime / "candidate-facts.json",
            "requirements": output / "Evidence/requirements.json",
            "match_analysis": output / "Evidence/match-analysis.json",
            "answer_plans": output / "Evidence/answer-plans.json",
            "research": output / "Evidence/research-sources.json",
            "manifest": output / "Reports/run-manifest.json",
        }
        for path in paths.values():
            reject_links(path)
        raw = {key: path.read_bytes() for key, path in paths.items()}
        hashes = {key: "sha256:" + hashlib.sha256(data).hexdigest() for key, data in raw.items()}
        # Validate after capture, then prove the validated bytes still match.
        # Otherwise a write between the first readiness check and read could be accepted.
        checked = self.inspect(reference)
        if not checked.ready:
            raise ValueError("Preparation changed during snapshot validation")
        if any(sha256_file(path) != hashes[key] for key, path in paths.items()):
            raise ValueError("Preparation files changed while taking the run snapshot")
        inputs = {key: json.loads(data.decode("utf-8")) for key, data in raw.items()}
        inputs["candidate"]["facts"] = [
            fact
            for fact in inputs["candidate"].get("facts", [])
            if fact.get("confidence") == "confirmed" and fact.get("sensitive") is False
        ]
        return {
            "reference": reference,
            "company": readiness.company,
            "role": readiness.role,
            "inputs": inputs,
            "hashes": hashes,
        }

    def simulation_dir(self, reference: str, run_id: str) -> Path:
        if not run_id.startswith("run-") or not all(c.isalnum() or c == "-" for c in run_id):
            raise ValueError("Invalid run ID")
        path = self.config.opportunity_output(parse_ref(reference)) / "Simulations" / run_id
        reject_symlink_path(path, self.config.output)
        return path
