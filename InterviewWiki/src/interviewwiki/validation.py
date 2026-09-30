from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from .artifacts import iter_preparation_artifacts
from .candidate import load_candidate_index
from .config import Config
from .opportunity import load_opportunity
from .profile import profile_photo_status
from .schemas import validate_data
from .util import ensure_within, parse_ref, read_json, sha256_file, sha256_paths, utc_now, write_json


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    path: str | None = None


ARTIFACT_SCHEMAS = {
    "requirements.json": "requirements",
    "match-analysis.json": "match-analysis",
    "answer-plans.json": "answer-plans",
    "resume-content.json": "resume-content",
    "claim-ledger.json": "claim-ledger",
    "research-sources.json": "research-sources",
}


def _fact_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "fact_ids" and isinstance(item, list):
                yield from (str(entry) for entry in item)
            else:
                yield from _fact_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _fact_refs(item)


def _requirement_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"requirement_id", "requirement_ids"}:
                if isinstance(item, list):
                    yield from (str(entry) for entry in item)
                elif isinstance(item, str):
                    yield item
            else:
                yield from _requirement_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _requirement_refs(item)


def _resume_blocks(locale: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("block_id"):
                result[str(value["block_id"])] = set(map(str, value.get("fact_ids", [])))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(locale)
    return result


class _ResumeHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.external_assets: list[str] = []
        self.inline_handlers: list[str] = []
        self.section_ids: list[str] = []
        self.profile_photos: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if values.get("data-section-id"):
            self.section_ids.append(str(values["data-section-id"]))
        if tag == "img" and "profile-photo" in str(values.get("class", "")).split():
            self.profile_photos.append(str(values.get("src", "")))
        for key in values:
            if key == "style" or key.startswith("on"):
                self.inline_handlers.append(key)
        for key in ("src", "href"):
            value = values.get(key) or ""
            if tag in {"script", "link", "img"} and value.startswith(("http://", "https://", "//")):
                self.external_assets.append(value)


def _numeric_tokens(text: str) -> set[str]:
    normalized: set[str] = set()
    for token in re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?", text):
        suffix = "%" if token.endswith("%") else ""
        value = token.removesuffix("%").replace(",", "")
        if value.isdigit():
            value = str(int(value))
        normalized.add(value + suffix)
    return normalized


def _normalized_resume_bullet(text: str) -> str:
    """Normalize visible bullet text for deterministic duplicate detection."""
    return re.sub(r"[\W_]+", "", " ".join(text.split()).casefold(), flags=re.UNICODE)


def _fact_support_text(fact: dict[str, Any]) -> str:
    values: list[str] = [str(fact.get("statement", ""))]

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif value is not None:
            values.append(str(value))

    collect(fact.get("qualifiers") or {})
    return " ".join(values)


def _grounded_text_nodes(value: Any) -> Iterable[tuple[str, list[str]]]:
    if isinstance(value, dict):
        fact_ids = value.get("fact_ids")
        if isinstance(fact_ids, list) and fact_ids:
            text = " ".join(
                str(value.get(key, ""))
                for key in ("text", "analysis", "reference_answer", "heading", "subheading", "period", "body")
            )
            if text.strip():
                yield text, [str(fact_id) for fact_id in fact_ids]
        for item in value.values():
            yield from _grounded_text_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _grounded_text_nodes(item)


def _claimable_nodes(value: Any) -> Iterable[tuple[str, str, list[str]]]:
    if isinstance(value, dict):
        block_id = value.get("block_id")
        fact_ids = value.get("fact_ids")
        if block_id and isinstance(fact_ids, list) and fact_ids:
            text = " ".join(" ".join(
                str(value.get(key, ""))
                for key in ("text", "label", "language", "level", "institution", "detail", "period", "year", "company", "role", "title")
            ).split())
            if text:
                yield str(block_id), text, [str(item) for item in fact_ids]
        for item in value.values():
            yield from _claimable_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _claimable_nodes(item)


def validate_run(config: Config, reference: str, *, strict: bool = False, task_kind: str | None = None, write_report: bool = True) -> dict[str, Any]:
    parsed, _ = load_opportunity(config, reference)
    output = config.opportunity_output(parsed)
    evidence = output / "Evidence"
    issues: list[Issue] = []
    data_by_name: dict[str, Any] = {}

    task_manifest_path = output / "Reports/task-manifest.json"
    if task_kind is None and task_manifest_path.is_file():
        task_kind = str(read_json(task_manifest_path).get("task_kind") or "full-package")
    task_kind = task_kind or "full-package"
    required_by_task = {
        "full-package": {"requirements.json", "match-analysis.json", "answer-plans.json", "resume-content.json", "claim-ledger.json", "research-sources.json"},
        "compatibility-review": {"requirements.json", "match-analysis.json", "research-sources.json"},
        "research-refresh": {"research-sources.json"},
        "requirements-review": {"requirements.json", "research-sources.json"},
        "interview-qa": {"requirements.json", "match-analysis.json", "answer-plans.json", "claim-ledger.json", "research-sources.json"},
        "portfolio-selection": {"requirements.json", "match-analysis.json", "research-sources.json"},
        "resume-content": {"requirements.json", "match-analysis.json", "resume-content.json", "claim-ledger.json", "research-sources.json"},
        "resume-render": {"resume-content.json", "claim-ledger.json"},
        "validation-audit": set(),
    }
    if task_kind not in required_by_task:
        issues.append(Issue("error", "task-kind", f"Unknown task kind: {task_kind}", "Reports/task-manifest.json"))
    required_artifacts = required_by_task.get(task_kind, set())

    candidate_index = load_candidate_index(config, rebuild=write_report)
    for detail in validate_data(config, "candidate-facts", candidate_index):
        issues.append(Issue("error", "candidate-schema", detail, ".interviewwiki/candidate-facts.json"))
    facts = {item["fact_id"]: item for item in candidate_index.get("facts", [])}
    if strict and not facts:
        issues.append(Issue("error", "candidate-empty", "PersonalWiki contains no indexed candidate facts"))

    for filename, schema in ARTIFACT_SCHEMAS.items():
        if filename not in required_artifacts:
            continue
        path = evidence / filename
        relative = path.relative_to(config.root).as_posix()
        if not path.is_file():
            issues.append(Issue("error", "missing-artifact", f"Missing {filename}", relative))
            continue
        try:
            data = read_json(path)
        except Exception as exc:
            issues.append(Issue("error", "invalid-json", str(exc), relative))
            continue
        data_by_name[filename] = data
        for detail in validate_data(config, schema, data):
            issues.append(Issue("error", "schema", detail, relative))
        if data.get("opportunity") != reference:
            issues.append(Issue("error", "wrong-opportunity", "Artifact targets another opportunity", relative))

    for filename, data in data_by_name.items():
        for fact_id in sorted(set(_fact_refs(data))):
            fact = facts.get(fact_id)
            if fact is None:
                issues.append(Issue("error", "unknown-fact", f"Unknown candidate fact: {fact_id}", filename))
            elif strict and fact.get("confidence") != "confirmed":
                issues.append(Issue("error", "unconfirmed-fact", f"Fact is not confirmed: {fact_id}", filename))

    requirements = data_by_name.get("requirements.json", {}).get("requirements", [])
    requirement_ids = {str(item.get("requirement_id")) for item in requirements}
    if len(requirement_ids) != len(requirements):
        issues.append(Issue("error", "duplicate-requirement", "Requirement IDs must be unique", "requirements.json"))
    known_sources = set()
    source_path = evidence / "opportunity-sources.json"
    if source_path.is_file():
        opportunity_sources = read_json(source_path).get("sources", [])
        known_sources.update(item.get("source_id") for item in opportunity_sources)
        opportunity_root = config.opportunity_source(parsed)
        for record in opportunity_sources:
            try:
                original = ensure_within(opportunity_root / str(record.get("path", "")), opportunity_root, must_exist=True)
                derived = ensure_within(
                    opportunity_root / str(record.get("derived_path", "")), opportunity_root, must_exist=True
                )
            except Exception as exc:
                issues.append(Issue("error", "opportunity-source-missing", str(exc), "opportunity-sources.json"))
                continue
            if sha256_file(original) != record.get("content_hash"):
                issues.append(Issue("error", "opportunity-source-changed", f"Source changed: {record.get('source_id')}", "opportunity-sources.json"))
            if sha256_file(derived) != record.get("derived_hash"):
                issues.append(Issue("error", "derived-source-changed", f"Derived evidence changed: {record.get('source_id')}", "opportunity-sources.json"))
    research_path = evidence / "research-sources.json"
    if research_path.is_file():
        research_data = read_json(research_path)
        known_sources.update(item.get("source_id") for item in research_data.get("sources", []))
        opportunity_root = config.opportunity_source(parsed)
        for record in research_data.get("sources", []):
            try:
                snapshot = ensure_within(opportunity_root / str(record.get("snapshot", "")), opportunity_root / "sources", must_exist=True)
            except Exception as exc:
                issues.append(Issue("error", "research-source-missing", str(exc), "research-sources.json"))
                continue
            if snapshot.is_symlink():
                issues.append(Issue("error", "research-source-symlink", f"Research snapshot is a symlink: {record.get('source_id')}", "research-sources.json"))
            elif sha256_file(snapshot) != record.get("content_hash"):
                issues.append(Issue("error", "research-source-changed", f"Research snapshot changed: {record.get('source_id')}", "research-sources.json"))
            excerpt = " ".join(str(record.get("excerpt", "")).split())
            if excerpt and excerpt not in " ".join(snapshot.read_text(encoding="utf-8").split()):
                issues.append(Issue("error", "research-excerpt-missing", f"Research excerpt is not present: {record.get('source_id')}", "research-sources.json"))
    for item in requirements:
        for citation in item.get("evidence", []):
            if citation.get("source_id") not in known_sources:
                issues.append(Issue("error", "unknown-opportunity-source", f"Unknown source: {citation.get('source_id')}", "requirements.json"))
    if strict and requirements and "source_coverage" not in data_by_name.get("requirements.json", {}):
        issues.append(Issue("warning", "source-coverage-missing", "Requirements do not include source-section coverage dispositions", "requirements.json"))

    for filename, data in data_by_name.items():
        if filename == "requirements.json":
            continue
        for requirement_id in sorted(set(_requirement_refs(data))):
            if requirement_id not in requirement_ids:
                issues.append(Issue("error", "unknown-requirement", f"Unknown requirement: {requirement_id}", filename))

    matches = data_by_name.get("match-analysis.json", {}).get("matches", [])
    match_ids = [str(item.get("requirement_id")) for item in matches]
    if strict and "match-analysis.json" in data_by_name and set(match_ids) != requirement_ids:
        missing = sorted(requirement_ids - set(match_ids))
        extra = sorted(set(match_ids) - requirement_ids)
        issues.append(Issue("error", "requirement-coverage", f"Match coverage differs; missing={missing}, extra={extra}", "match-analysis.json"))
    if len(match_ids) != len(set(match_ids)):
        issues.append(Issue("error", "duplicate-match", "Each requirement may have one match record", "match-analysis.json"))
    for match in matches:
        status = match.get("status")
        if status in {"match", "partial"} and not match.get("fact_ids"):
            issues.append(Issue("error", "ungrounded-match", "Match/partial status requires candidate facts", "match-analysis.json"))
        if status in {"gap", "unknown"} and match.get("fact_ids"):
            issues.append(Issue("warning", "gap-with-facts", "Gap/unknown record also lists candidate facts; review status", "match-analysis.json"))

    minimum_questions = int((config.settings.get("workflow") or {}).get("minimum_questions", 5))
    questions = data_by_name.get("answer-plans.json", {}).get("questions", [])
    if strict and "answer-plans.json" in data_by_name and len(questions) < minimum_questions:
        issues.append(Issue("error", "question-count", f"At least {minimum_questions} grounded questions are required", "answer-plans.json"))

    resume = data_by_name.get("resume-content.json", {})
    locales = resume.get("locales", {})
    if "en" in locales and "ja" in locales:
        en_blocks = _resume_blocks(locales["en"])
        ja_blocks = _resume_blocks(locales["ja"])
        if set(en_blocks) != set(ja_blocks):
            issues.append(Issue("error", "bilingual-block-parity", "English and Japanese resume block IDs differ", "resume-content.json"))
        for block_id in sorted(set(en_blocks) & set(ja_blocks)):
            if en_blocks[block_id] != ja_blocks[block_id]:
                issues.append(Issue("error", "bilingual-fact-parity", f"Fact IDs differ for block {block_id}", "resume-content.json"))

        employment_starts = {
            fact_id: str((fact.get("qualifiers") or {}).get("start_date", ""))
            for fact_id, fact in facts.items()
            if fact.get("kind") == "employment" and (fact.get("qualifiers") or {}).get("start_date")
        }
        for locale_name, locale in locales.items():
            for experience in locale.get("professional_experience", []):
                role_label = f"{experience.get('company', '')} / {experience.get('role', '')}".strip(" /")
                all_bullets: list[tuple[str, str]] = []
                for category in ("responsibilities", "achievements"):
                    bullets = list(experience.get(category, []))
                    if strict and not 2 <= len(bullets) <= 3:
                        issues.append(Issue(
                            "error", "experience-bullet-count",
                            f"{locale_name} {role_label} requires two or three distinct {category}; found {len(bullets)}",
                            "resume-content.json",
                        ))
                    normalized = [_normalized_resume_bullet(str(item.get("text", ""))) for item in bullets]
                    if strict and len(normalized) != len(set(normalized)):
                        issues.append(Issue(
                            "error", "duplicate-experience-bullet",
                            f"{locale_name} {role_label} repeats a {category} bullet",
                            "resume-content.json",
                        ))
                    all_bullets.extend((category, value) for value in normalized if value)
                visible = [value for _category, value in all_bullets]
                if strict and len(visible) != len(set(visible)):
                    issues.append(Issue(
                        "error", "duplicate-experience-bullet",
                        f"{locale_name} {role_label} repeats content across Responsibilities and Key Achievements",
                        "resume-content.json",
                    ))

            if strict:
                self_pr_fact_ids = {
                    str(fact_id)
                    for paragraph in locale.get("self_pr", [])
                    for fact_id in paragraph.get("fact_ids", [])
                }
                if len(self_pr_fact_ids) < 2:
                    issues.append(Issue(
                        "error", "self-pr-evidence-breadth",
                        f"{locale_name} Self PR must connect at least two distinct candidate facts",
                        "resume-content.json",
                    ))
                available_kinds = {str(fact.get("kind")) for fact in facts.values()}
                referenced_kinds = {
                    str(facts[fact_id].get("kind"))
                    for fact_id in self_pr_fact_ids
                    if fact_id in facts
                }
                if "employment" in available_kinds and "employment" not in referenced_kinds:
                    issues.append(Issue(
                        "error", "self-pr-career-grounding",
                        f"{locale_name} Self PR must ground career direction in confirmed employment experience",
                        "resume-content.json",
                    ))
                concrete_kinds = {"responsibility", "achievement", "project", "portfolio"}
                if available_kinds & concrete_kinds and not referenced_kinds & concrete_kinds:
                    issues.append(Issue(
                        "error", "self-pr-case-grounding",
                        f"{locale_name} Self PR must reference a concrete responsibility, achievement, project, or portfolio case",
                        "resume-content.json",
                    ))

            professional_fact_ids = {
                str(fact_id)
                for item in locale.get("professional_experience", [])
                for fact_id in item.get("fact_ids", [])
                if str(fact_id) in employment_starts
            }
            if professional_fact_ids:
                oldest_recent_start = min(employment_starts[fact_id] for fact_id in professional_fact_ids)
                expected_earlier = {
                    fact_id for fact_id, start in employment_starts.items() if start < oldest_recent_start
                }
                actual_earlier = {
                    str(fact_id)
                    for item in locale.get("earlier_career", [])
                    for fact_id in item.get("fact_ids", [])
                }
                missing_earlier = sorted(expected_earlier - actual_earlier)
                if missing_earlier:
                    issues.append(Issue(
                        "error", "earlier-career-coverage",
                        f"{locale_name} earlier career omits employment facts: {missing_earlier}",
                        "resume-content.json",
                    ))

    ledger = data_by_name.get("claim-ledger.json", {}).get("claims", [])
    claim_ids = [str(item.get("claim_id")) for item in ledger]
    if len(claim_ids) != len(set(claim_ids)):
        issues.append(Issue("error", "duplicate-claim", "Claim IDs must be unique", "claim-ledger.json"))
    fact_statements = {fact_id: _fact_support_text(item) for fact_id, item in facts.items()}
    for filename, data in data_by_name.items():
        if filename == "claim-ledger.json":
            continue
        for text, fact_ids in _grounded_text_nodes(data):
            supported_text = " ".join(fact_statements.get(fact_id, "") for fact_id in fact_ids)
            unsupported_numbers = _numeric_tokens(text) - _numeric_tokens(supported_text)
            if unsupported_numbers:
                issues.append(
                    Issue(
                        "error",
                        "unsupported-number",
                        f"Grounded text contains unsupported values: {sorted(unsupported_numbers)}",
                        filename,
                    )
                )
    for claim in ledger:
        if claim.get("validation") != "supported":
            requires_supported = claim.get("artifact") == "Resume/index.html" or claim.get("validation") == "unsupported"
            severity = "error" if strict and requires_supported else "warning"
            issues.append(Issue(severity, "unsupported-claim", f"Claim is {claim.get('validation')}: {claim.get('claim_id')}", "claim-ledger.json"))
        supported_text = " ".join(fact_statements.get(fact_id, "") for fact_id in claim.get("fact_ids", []))
        unsupported_numbers = _numeric_tokens(str(claim.get("text", ""))) - _numeric_tokens(supported_text)
        if unsupported_numbers:
            issues.append(Issue("error", "unsupported-number", f"Claim {claim.get('claim_id')} contains unsupported values: {sorted(unsupported_numbers)}", "claim-ledger.json"))
    if strict and "claim-ledger.json" in data_by_name and not ledger:
        issues.append(Issue("error", "claim-ledger-empty", "Strict validation requires candidate claim records", "claim-ledger.json"))

    if strict and "resume-content.json" in data_by_name and "claim-ledger.json" in data_by_name:
        ledger_blocks = {str(item.get("block_id")) for item in ledger if item.get("block_id")}
        for locale_name, locale in data_by_name["resume-content.json"].get("locales", {}).items():
            for block_id, _text_value, _fact_ids_value in _claimable_nodes(locale):
                if block_id not in ledger_blocks:
                    issues.append(Issue("error", "claim-ledger-coverage", f"Resume block is not in the claim ledger: {locale_name}/{block_id}", "claim-ledger.json"))
        resume_claims = {
            str(item.get("block_id")): item
            for item in ledger
            if item.get("artifact") == "Resume/index.html" and item.get("block_id")
        }
        for block_id, text_value, fact_ids_value in _claimable_nodes(
            data_by_name["resume-content.json"].get("locales", {}).get("en", {})
        ):
            claim = resume_claims.get(block_id)
            if claim and (
                " ".join(str(claim.get("text", "")).split()) != text_value
                or set(map(str, claim.get("fact_ids", []))) != set(fact_ids_value)
            ):
                issues.append(Issue(
                    "error", "claim-ledger-stale",
                    f"Resume claim no longer matches structured block: {block_id}",
                    "claim-ledger.json",
                ))
    if strict and "answer-plans.json" in data_by_name and "claim-ledger.json" in data_by_name:
        ledger_blocks = {str(item.get("block_id")) for item in ledger if item.get("block_id")}
        for question in data_by_name["answer-plans.json"].get("questions", []):
            block_id = str(question.get("question_id", ""))
            if block_id and block_id not in ledger_blocks:
                issues.append(Issue("error", "claim-ledger-coverage", f"Interview answer is not in the claim ledger: {block_id}", "claim-ledger.json"))

    markdown_required = []
    if task_kind in {"full-package", "compatibility-review", "portfolio-selection"}:
        markdown_required.append("Interview/candidate-analysis.md")
    if task_kind in {"full-package", "interview-qa"}:
        markdown_required.append("Interview/interview-q-and-a.md")
    for relative in markdown_required:
        path = output / relative
        if not path.is_file():
            issues.append(Issue("error", "missing-artifact", f"Missing {relative}", relative))
        elif strict and re.search(r"\b(?:TODO|generation pending)\b", path.read_text(encoding="utf-8"), re.IGNORECASE):
            issues.append(Issue("error", "unfinished-artifact", "Artifact still contains a placeholder", relative))

    html_required = task_kind in {"full-package", "resume-render"}
    html_path = output / "Resume/index.html"
    if strict and html_required and not html_path.is_file():
        issues.append(Issue("error", "resume-not-rendered", "Bilingual resume HTML has not been rendered", "Resume/index.html"))
    elif html_path.is_file() and (strict or html_required):
        parser = _ResumeHTML()
        parser.feed(html_path.read_text(encoding="utf-8"))
        for required_id in ("resume-en", "resume-ja"):
            if required_id not in parser.ids:
                issues.append(Issue("error", "resume-locale", f"Resume HTML is missing {required_id}", "Resume/index.html"))
        if parser.external_assets:
            issues.append(Issue("error", "external-resume-asset", f"Resume uses external rendering assets: {parser.external_assets}", "Resume/index.html"))
        if parser.inline_handlers:
            issues.append(Issue("error", "inline-resume-code", f"Resume contains inline style/event attributes: {sorted(set(parser.inline_handlers))}", "Resume/index.html"))
        photo_status = profile_photo_status(config)
        if not photo_status.get("valid"):
            issues.append(Issue("error", "profile-photo-invalid", str(photo_status.get("error")), "PersonalWiki/raw/media"))
        elif photo_status.get("detected"):
            expected_photo = "assets/profile" + Path(str(photo_status["path"])).suffix.lower()
            if parser.profile_photos != [expected_photo, expected_photo]:
                issues.append(Issue(
                    "error", "profile-photo-missing",
                    f"Both locale resumes must use {expected_photo}; found {parser.profile_photos}",
                    "Resume/index.html",
                ))
            copied_photo = output / "Resume" / expected_photo
            if not copied_photo.is_file() or sha256_file(copied_photo) != photo_status.get("content_hash"):
                issues.append(Issue("error", "profile-photo-stale", "Rendered profile photo is missing or stale", expected_photo))
        expected_sections = ["self-introduction", "signals", "professional-experience", "personal-expertise", "self-pr"] * 2
        if parser.section_ids != expected_sections:
            issues.append(Issue("error", "method-section-order", f"Method section order differs: {parser.section_ids}", "Resume/index.html"))
        html_text = html_path.read_text(encoding="utf-8")
        for locale_id in ("resume-en", "resume-ja"):
            start = html_text.find(f'id="{locale_id}"')
            if start >= 0:
                end = html_text.find("</article>", start)
                locale_html = html_text[start:end]
                if locale_html.find('<aside class="sidebar">') > locale_html.find('<main class="main">'):
                    issues.append(Issue("error", "method-dom-order", f"Method sidebar must precede main content for {locale_id}", "Resume/index.html"))

    for pdf_path in sorted((output / "Resume").glob("*.pdf")) if (output / "Resume").is_dir() else []:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            pdf_text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if "file://" in pdf_text or re.search(r"/(?:Users|Volumes)/", pdf_text) or re.search(r"[A-Za-z]:\\\\Users\\\\", pdf_text):
                issues.append(Issue("error", "pdf-local-path", f"PDF contains a local filesystem path: {pdf_path.name}", f"Resume/{pdf_path.name}"))
            if not reader.pages:
                issues.append(Issue("error", "pdf-empty", f"PDF has no pages: {pdf_path.name}", f"Resume/{pdf_path.name}"))
        except Exception as exc:
            issues.append(Issue("error", "pdf-invalid", f"Could not inspect {pdf_path.name}: {exc}", f"Resume/{pdf_path.name}"))

    manifest_path = output / "Reports/run-manifest.json"
    if strict:
        if not manifest_path.is_file():
            issues.append(Issue("error", "manifest-missing", "Strict validation requires a run manifest", "Reports/run-manifest.json"))
        else:
            manifest = read_json(manifest_path)
            for detail in validate_data(config, "run-manifest", manifest):
                issues.append(Issue("error", "manifest-schema", detail, "Reports/run-manifest.json"))
            if manifest.get("opportunity") != reference or manifest.get("task_kind") != task_kind:
                issues.append(Issue("error", "manifest-target", "Run manifest opportunity/task does not match validation", "Reports/run-manifest.json"))
            expected_inputs = {
                "candidate_facts": candidate_index.get("content_hash"),
                "profile_photo": str(profile_photo_status(config).get("content_hash", "invalid")),
                "resume_template": sha256_paths([item for item in config.resume_template.rglob("*") if item.is_file()], config.resume_template),
            }
            if source_path.is_file():
                expected_inputs["opportunity_sources"] = sha256_file(source_path)
            for name, expected in expected_inputs.items():
                if manifest.get("inputs", {}).get(name) != expected:
                    issues.append(Issue("error", "manifest-input-stale", f"Manifest input is stale: {name}", "Reports/run-manifest.json"))
            if manifest.get("model") == "unknown":
                issues.append(Issue("warning", "manifest-model-unknown", "Set INTERVIEWWIKI_AGENT_MODEL for reproducible agent runs", "Reports/run-manifest.json"))
            if manifest.get("completed_at"):
                listed = manifest.get("outputs", {})
                actual = {item.relative_to(output).as_posix() for item in iter_preparation_artifacts(output)}
                unlisted = sorted(actual - set(listed))
                missing = sorted(set(listed) - actual)
                if unlisted:
                    issues.append(Issue("error", "manifest-output-unlisted", f"Manifest omits outputs: {unlisted}", "Reports/run-manifest.json"))
                if missing:
                    issues.append(Issue("error", "manifest-output-missing", f"Manifest lists missing outputs: {missing}", "Reports/run-manifest.json"))
                for relative, expected in listed.items():
                    artifact = output / str(relative)
                    if not artifact.is_file() or sha256_file(artifact) != expected:
                        issues.append(Issue("error", "manifest-output-stale", f"Manifest output is stale: {relative}", "Reports/run-manifest.json"))

    counts = {severity: sum(item.severity == severity for item in issues) for severity in ("error", "warning", "suggestion")}
    report = {
        "schema_version": 1,
        "opportunity": reference,
        "task_kind": task_kind,
        "strict": strict,
        "validated_at": utc_now(),
        "valid": counts["error"] == 0,
        "counts": counts,
        "issues": [asdict(item) for item in issues],
    }
    if write_report:
        write_json(output / "Reports/validation.json", report)
    return report
