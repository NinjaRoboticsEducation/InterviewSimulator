from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate import build_candidate_index, candidate_status, migrate_candidate_index, personal_status, search_candidate
from .config import Config
from .errors import ValidationFailure
from .migration import upgrade_legacy_output
from .opportunity import ingest_opportunity, initialize_opportunity, register_opportunity, register_research
from .resume import render_resume
from .validation import validate_run
from .workflow import finalize_manifest, initialize_project, prepare_run


class InterviewWikiService:
    """Stable application boundary shared by CLI, skills, and optional MCP."""

    def __init__(self, root: Path | str = ".") -> None:
        self.config = Config.load(root)

    def initialize(self) -> None:
        initialize_project(self.config)

    def opportunity_create(self, company: str, role: str, opportunity: str | None = None) -> str:
        return initialize_opportunity(self.config, company, role, opportunity)

    def opportunity_ingest(self, reference: str) -> dict[str, Any]:
        return ingest_opportunity(self.config, reference)

    def candidate_build(self) -> dict[str, Any]:
        return build_candidate_index(self.config)

    def personal_status(self) -> dict[str, Any]:
        return personal_status(self.config)

    def candidate_status(self) -> dict[str, Any]:
        return candidate_status(self.config)

    def candidate_migrate(self) -> dict[str, Any]:
        return migrate_candidate_index(self.config)

    def candidate_search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return search_candidate(self.config, query, limit)

    def opportunity_register(self, value: str) -> dict[str, Any]:
        return register_opportunity(self.config, value)

    def run_prepare(self, reference: str, task_kind: str = "full-package") -> dict[str, Any]:
        return prepare_run(self.config, reference, task_kind)

    def run_validate(self, reference: str, strict: bool = False, task_kind: str | None = None) -> dict[str, Any]:
        return validate_run(self.config, reference, strict=strict, task_kind=task_kind)

    def resume_render(self, reference: str, create_pdf: bool | str = False) -> dict[str, str]:
        # Preflight structured resume inputs only. Existing rendered files may be
        # stale by definition and must not prevent the renderer from replacing them.
        report = validate_run(self.config, reference, strict=False, task_kind="resume-content")
        if not report["valid"]:
            raise ValidationFailure(
                "Resume cannot be rendered until non-strict validation passes; "
                "inspect Output/<company>/<opportunity>/Reports/validation.json"
            )
        return render_resume(self.config, reference, create_pdf=create_pdf)

    def resume_upgrade(self, reference: str) -> dict[str, Any]:
        return upgrade_legacy_output(self.config, reference)

    def manifest_finalize(self, reference: str, task_kind: str | None = None) -> dict[str, Any]:
        return finalize_manifest(self.config, reference, task_kind)

    def research_register(self, reference: str, **kwargs: Any) -> dict[str, Any]:
        return register_research(self.config, reference, **kwargs)
