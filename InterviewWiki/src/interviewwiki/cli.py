from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .errors import InterviewWikiError
from .service import InterviewWikiService
from .profile import profile_photo_status


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="interviewwiki", description="Evidence-grounded interview preparation")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize portable project directories")
    sub.add_parser("doctor", help="Inspect project setup")

    personal = sub.add_parser("personal", help="Inspect PersonalWiki readiness")
    personal_sub = personal.add_subparsers(dest="personal_command", required=True)
    personal_sub.add_parser("status")

    opportunity = sub.add_parser("opportunity", help="Create or ingest an opportunity")
    opportunity_sub = opportunity.add_subparsers(dest="opportunity_command", required=True)
    new = opportunity_sub.add_parser("new")
    new.add_argument("--company", required=True)
    new.add_argument("--role", required=True)
    new.add_argument("--opportunity")
    ingest = opportunity_sub.add_parser("ingest")
    ingest.add_argument("reference")
    register_opportunity = opportunity_sub.add_parser("register")
    register_opportunity.add_argument("folder")

    candidate = sub.add_parser("candidate", help="Build or query local candidate facts")
    candidate_sub = candidate.add_subparsers(dest="candidate_command", required=True)
    candidate_sub.add_parser("build")
    candidate_sub.add_parser("status")
    candidate_sub.add_parser("migrate")
    search = candidate_sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)

    research = sub.add_parser("research", help="Register a captured public research snapshot")
    research_sub = research.add_subparsers(dest="research_command", required=True)
    register = research_sub.add_parser("register")
    register.add_argument("reference")
    register.add_argument("--source-id", required=True)
    register.add_argument("--url", required=True)
    register.add_argument("--title", required=True)
    register.add_argument("--publisher", required=True)
    register.add_argument("--snapshot", required=True)
    register.add_argument("--source-tier", required=True, choices=["official", "primary", "reputable-secondary", "anecdotal"])
    register.add_argument("--excerpt", default="")
    register.add_argument("--claim-type", default="direct", choices=["direct", "analyst-inference"])
    register.add_argument("--published-at", default="")

    run = sub.add_parser("run", help="Prepare or finalize an opportunity run")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    prepare = run_sub.add_parser("prepare")
    prepare.add_argument("reference")
    prepare.add_argument("--task-kind", default="full-package")
    finalize = run_sub.add_parser("finalize")
    finalize.add_argument("reference")
    finalize.add_argument("--task-kind")

    task = sub.add_parser("task", help="Prepare, validate, or finalize a focused task")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_prepare = task_sub.add_parser("prepare")
    task_prepare.add_argument("reference")
    task_prepare.add_argument("--kind", required=True)
    task_validate = task_sub.add_parser("validate")
    task_validate.add_argument("reference")
    task_validate.add_argument("--kind", required=True)
    task_validate.add_argument("--strict", action="store_true")
    task_finalize = task_sub.add_parser("finalize")
    task_finalize.add_argument("reference")
    task_finalize.add_argument("--kind", required=True)

    resume = sub.add_parser("resume", help="Render the canonical bilingual resume")
    resume_sub = resume.add_subparsers(dest="resume_command", required=True)
    render = resume_sub.add_parser("render")
    render.add_argument("reference")
    render.add_argument("--pdf", nargs="?", const="bilingual", choices=["en", "ja", "bilingual", "all"])
    upgrade = resume_sub.add_parser("upgrade", help="Recoverably convert a generated schema-v1 resume to Method v1")
    upgrade.add_argument("reference")

    validate = sub.add_parser("validate", help="Validate one opportunity output")
    validate.add_argument("reference")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--task-kind")
    return parser


def doctor(service: InterviewWikiService) -> dict[str, Any]:
    config = service.config
    return {
        "version": __version__,
        "project": str(config.root),
        "portable_paths": all(
            path.is_relative_to(config.root)
            for path in (config.job_descriptions, config.personal_wiki, config.output, config.runtime, config.resume_template)
        ),
        "job_descriptions": config.job_descriptions.is_dir(),
        "personal_wiki": config.personal_wiki.is_dir(),
        "personal_wiki_config": (config.personal_wiki / "llmwiki.yaml").is_file(),
        "resume_template": (config.resume_template / "index.html.tpl").is_file(),
        "profile_photo": profile_photo_status(config),
        "schemas": len(list((config.root / "schemas").glob("*.schema.json"))),
    }


def execute(args: argparse.Namespace, service: InterviewWikiService) -> tuple[Any, int]:
    if args.command == "init":
        service.initialize()
        return {"initialized": True, "project": str(service.config.root)}, 0
    if args.command == "doctor":
        result = doctor(service)
        checks = [value for key, value in result.items() if key not in {"version", "project", "schemas", "profile_photo"}]
        return result, 0 if all(checks) and result["profile_photo"]["valid"] and result["schemas"] >= 6 else 1
    if args.command == "personal" and args.personal_command == "status":
        result = service.personal_status()
        return result, 0 if result["ready"] else 1
    if args.command == "opportunity" and args.opportunity_command == "new":
        reference = service.opportunity_create(args.company, args.role, args.opportunity)
        return {"created": reference}, 0
    if args.command == "opportunity" and args.opportunity_command == "ingest":
        return service.opportunity_ingest(args.reference), 0
    if args.command == "opportunity" and args.opportunity_command == "register":
        return service.opportunity_register(args.folder), 0
    if args.command == "candidate" and args.candidate_command == "build":
        return service.candidate_build(), 0
    if args.command == "candidate" and args.candidate_command == "status":
        result = service.candidate_status()
        return result, 0 if result["personal_wiki"]["ready"] else 1
    if args.command == "candidate" and args.candidate_command == "migrate":
        return service.candidate_migrate(), 0
    if args.command == "candidate" and args.candidate_command == "search":
        return service.candidate_search(args.query, args.limit), 0
    if args.command == "research" and args.research_command == "register":
        return service.research_register(
            args.reference,
            source_id=args.source_id,
            url=args.url,
            title=args.title,
            publisher=args.publisher,
            snapshot=args.snapshot,
            source_tier=args.source_tier,
            excerpt=args.excerpt,
            claim_type=args.claim_type,
            published_at=args.published_at,
        ), 0
    if args.command == "run" and args.run_command == "prepare":
        return service.run_prepare(args.reference, args.task_kind), 0
    if args.command == "run" and args.run_command == "finalize":
        return service.manifest_finalize(args.reference, args.task_kind), 0
    if args.command == "task" and args.task_command == "prepare":
        return service.run_prepare(args.reference, args.kind), 0
    if args.command == "task" and args.task_command == "validate":
        result = service.run_validate(args.reference, args.strict, args.kind)
        return result, 0 if result["valid"] else 1
    if args.command == "task" and args.task_command == "finalize":
        return service.manifest_finalize(args.reference, args.kind), 0
    if args.command == "resume" and args.resume_command == "render":
        return service.resume_render(args.reference, args.pdf or False), 0
    if args.command == "resume" and args.resume_command == "upgrade":
        return service.resume_upgrade(args.reference), 0
    if args.command == "validate":
        result = service.run_validate(args.reference, args.strict, args.task_kind)
        return result, 0 if result["valid"] else 1
    raise InterviewWikiError("Unsupported command")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        service = InterviewWikiService(Path.cwd())
        data, status = execute(args, service)
        _print(data)
    except InterviewWikiError as exc:
        _print({"error": str(exc)})
        status = 2
    raise SystemExit(status)


if __name__ == "__main__":
    main(sys.argv[1:])
