from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import InterviewWikiError
from .service import InterviewWikiService


def build_server(root: Path | str = ".") -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise InterviewWikiError("MCP support is optional; install with 'uv sync --extra mcp'") from exc

    service = InterviewWikiService(root)
    server = FastMCP("InterviewWiki")

    @server.tool()
    def interview_candidate_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search local, evidence-backed candidate facts without changing PersonalWiki."""
        return service.candidate_search(query, limit)

    @server.tool()
    def interview_personal_status() -> dict[str, Any]:
        """Check strict PersonalWiki readiness without modifying candidate content."""
        return service.personal_status()

    @server.tool()
    def interview_candidate_migrate() -> dict[str, Any]:
        """Refresh derived candidate facts and return a post-run walkthrough."""
        return service.candidate_migrate()

    @server.tool()
    def interview_opportunity_register(folder: str) -> dict[str, Any]:
        """Register and ingest a two-level opportunity folder inside JobDescriptions."""
        return service.opportunity_register(folder)

    @server.tool()
    def interview_opportunity_ingest(reference: str) -> dict[str, Any]:
        """Normalize and hash sources for one registered company/opportunity ID."""
        return service.opportunity_ingest(reference)

    @server.tool()
    def interview_run_prepare(reference: str) -> dict[str, Any]:
        """Create missing structured output shells for one registered opportunity."""
        return service.run_prepare(reference)

    @server.tool()
    def interview_task_prepare(reference: str, task_kind: str) -> dict[str, Any]:
        """Prepare a full or focused task without creating unrelated placeholders."""
        return service.run_prepare(reference, task_kind)

    @server.tool()
    def interview_run_validate(reference: str, strict: bool = False) -> dict[str, Any]:
        """Validate schemas, grounding, bilingual parity, and output completeness."""
        return service.run_validate(reference, strict)

    @server.tool()
    def interview_resume_render(reference: str) -> dict[str, str]:
        """Render validated bilingual resume content with the canonical local template."""
        return service.resume_render(reference, False)

    return server


def main() -> None:
    build_server(Path.cwd()).run()


if __name__ == "__main__":
    main()
