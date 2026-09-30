from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import Config
from .errors import InterviewWikiError
from .opportunity import load_opportunity
from .schemas import validate_data
from .util import operation_lock, read_json, sha256_file, utc_now, write_json, write_text


def _section(locale: dict[str, Any], section_id: str) -> dict[str, Any]:
    return next((item for item in locale.get("sections", []) if item.get("section_id") == section_id), {})


def _claim(block_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"block_id": block_id, "text": str(item.get("text", "")).strip(), "fact_ids": list(item.get("fact_ids", []))}


def _labels(ja: bool) -> tuple[dict[str, str], dict[str, Any]]:
    sidebar = {
        "contact": "連絡先" if ja else "Contact", "languages": "言語" if ja else "Languages",
        "skills": "専門領域" if ja else "Skills", "tools": "ツール" if ja else "Tools",
        "education": "学歴" if ja else "Education", "awards": "受賞歴" if ja else "Awards",
    }
    sections = {
        "self_introduction": "自己紹介" if ja else "Self Introduction",
        "professional_experience": "職務経歴" if ja else "Professional Experience",
        "responsibilities": "担当業務" if ja else "Responsibilities",
        "achievements": "主な実績" if ja else "Key Achievements",
        "earlier_career": "その他の職務経歴" if ja else "Earlier Career",
        "earlier_headers": ["期間", "職位", "会社", "勤務地"] if ja else ["Period", "Title", "Company", "Location"],
        "expertise": "個人の専門領域" if ja else "Personal Expertise",
        "self_pr": "自己PR" if ja else "Self PR",
    }
    return sidebar, sections


def _legacy_locale(locale: dict[str, Any], ja: bool) -> dict[str, Any]:
    experience = _section(locale, "experience").get("items", [])
    skills = _section(locale, "skills").get("items", [])
    language_items = _section(locale, "languages").get("items", [])
    education_items = _section(locale, "education").get("items", [])
    groups = [*skills, *language_items]
    if len(groups) < 4:
        raise InterviewWikiError("Legacy resume needs at least four evidence groups for Method expertise/signals")

    sidebar_labels, section_labels = _labels(ja)
    languages = []
    for index, bullet in enumerate(language_items[0].get("bullets", []) if language_items else [], 1):
        text = str(bullet.get("text", "")).strip()
        parts = [part.strip() for part in text.split("—", 1)]
        languages.append({
            "block_id": f"language-{index}", "language": parts[0],
            "level": parts[1] if len(parts) == 2 else ("記載あり" if ja else "Listed"),
            "fact_ids": list(bullet.get("fact_ids", [])),
        })

    design_items = skills[:-1] if len(skills) > 1 else skills
    tool_items = skills[-1:] if skills else []
    skill_tags = [
        {"block_id": f"{item['block_id']}-tag-{index}", "text": bullet["text"], "fact_ids": list(bullet.get("fact_ids", []))}
        for item in design_items for index, bullet in enumerate(item.get("bullets", []), 1)
    ]
    tool_tags = [
        {"block_id": f"{item['block_id']}-tag-{index}", "text": bullet["text"], "fact_ids": list(bullet.get("fact_ids", []))}
        for item in tool_items for index, bullet in enumerate(item.get("bullets", []), 1)
    ]
    if not skill_tags or not tool_tags or not languages or not education_items:
        raise InterviewWikiError("Legacy resume lacks required Method sidebar evidence")

    education = [{
        "block_id": str(item["block_id"]), "institution": str(item.get("heading", "")),
        "detail": str(item.get("subheading", "")), "period": str(item.get("period", "")),
        "fact_ids": list(item.get("fact_ids", [])),
    } for item in education_items]
    summary = locale.get("summary") or {}
    intro = _claim("intro-summary", summary)
    self_pr = _claim("self-pr-summary", summary)
    professional = []
    for item in experience:
        item_facts = list(item.get("fact_ids", []))
        company = str(item.get("subheading", ""))
        role = str(item.get("heading", ""))
        achievements = [
            _claim(f"{item['block_id']}-achievement-{index}", bullet)
            for index, bullet in enumerate(item.get("bullets", []), 1)
        ]
        responsibility_text = (
            f"{company}で{role}を担当。" if ja else f"Served as {role} at {company}."
        )
        professional.append({
            "block_id": str(item["block_id"]), "company": company,
            "role": role, "period": str(item.get("period", "")), "location": "",
            "fact_ids": item_facts,
            "responsibilities": [{
                "block_id": f"{item['block_id']}-responsibility-1",
                "text": responsibility_text,
                "fact_ids": item_facts,
            }],
            "achievements": achievements,
        })

    signals = []
    expertise = []
    for index, item in enumerate(groups[:4], 1):
        bullets = list(item.get("bullets", []))
        facts = list(dict.fromkeys([*item.get("fact_ids", []), *(fact for bullet in bullets for fact in bullet.get("fact_ids", []))]))
        signals.append({
            "block_id": f"signal-{index}", "label": str(item.get("heading", "")),
            "text": str(bullets[0].get("text", item.get("heading", ""))) if bullets else str(item.get("heading", "")),
            "fact_ids": facts,
        })
        expertise.append({
            "block_id": f"expertise-{index}", "title": str(item.get("heading", "")), "fact_ids": facts,
            "bullets": [_claim(f"expertise-{index}-detail-{bullet_index}", bullet) for bullet_index, bullet in enumerate(bullets, 1)],
        })

    return {
        "name": str(locale.get("name", "")), "headline": str(locale.get("headline", "")),
        "sidebar": {"labels": sidebar_labels, "languages": languages, "skills": skill_tags, "tools": tool_tags, "education": education, "awards": []},
        "section_labels": section_labels, "self_introduction": [intro, {**intro, "block_id": "intro-summary-2"}], "signals": signals,
        "professional_experience": professional, "earlier_career": [], "expertise": expertise,
        "self_pr": [self_pr, {**self_pr, "block_id": "self-pr-summary-2"}],
    }


def _claimable(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("block_id") and value.get("fact_ids"):
            text = " ".join(str(value.get(key, "")) for key in (
                "text", "label", "language", "level", "institution", "detail", "period", "company", "role", "title"
            )).strip()
            if text:
                result.append({"block_id": str(value["block_id"]), "text": text, "fact_ids": list(value["fact_ids"])})
        for item in value.values():
            result.extend(_claimable(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_claimable(item))
    return result


def upgrade_legacy_output(config: Config, reference: str) -> dict[str, Any]:
    parsed, _ = load_opportunity(config, reference)
    output = config.opportunity_output(parsed)
    evidence = output / "Evidence"
    resume_path = evidence / "resume-content.json"
    if not resume_path.is_file():
        raise InterviewWikiError("No generated resume content exists to upgrade")
    legacy = read_json(resume_path)
    if legacy.get("schema_version") == 2:
        return {"opportunity": reference, "upgraded": False, "reason": "already-method-v1"}
    if legacy.get("schema_version") != 1:
        raise InterviewWikiError("Only legacy resume schema version 1 can be upgraded")

    source_hash = sha256_file(resume_path)
    digest = source_hash.split(":", 1)[1][:12]
    migration_id = f"method-v1-{digest}"
    backup = output / "Reports/migrations" / migration_id
    lock = config.runtime / "locks" / f"legacy-output-{'-'.join(parsed)}.lock"
    with operation_lock(lock):
        backup.mkdir(parents=True, exist_ok=True)
        affected = [resume_path, evidence / "claim-ledger.json", evidence / "research-sources.json"]
        for path in affected:
            if path.is_file() and not (backup / path.name).exists():
                shutil.copy2(path, backup / path.name)
        render_backup = backup / "Resume"
        for name in ("index.html", "styles.css", "script.js", "resume-en.pdf", "resume-ja.pdf", "resume-bilingual.pdf"):
            rendered = output / "Resume" / name
            if rendered.is_file():
                render_backup.mkdir(parents=True, exist_ok=True)
                destination = render_backup / name
                if not destination.exists():
                    shutil.move(rendered, destination)

        candidate = dict(legacy.get("candidate") or {})
        for key in ("email", "phone", "website", "location"):
            candidate.setdefault(key, "")
        candidate["consent_to_publish"] = True
        converted = {
            "schema_version": 2, "template_id": "method-v1", "opportunity": reference,
            "candidate": candidate,
            "locales": {
                "en": _legacy_locale(legacy["locales"]["en"], False),
                "ja": _legacy_locale(legacy["locales"]["ja"], True),
            },
        }
        errors = validate_data(config, "resume-content", converted)
        if errors:
            raise InterviewWikiError("Legacy Method conversion failed: " + "; ".join(errors))
        write_json(resume_path, converted)

        research_path = evidence / "research-sources.json"
        if research_path.is_file():
            research = read_json(research_path)
            for source in research.get("sources", []):
                source.setdefault("excerpt", "")
                source.setdefault("claim_type", "direct")
                source.setdefault("query_classification", "company-role-only")
                source.setdefault("published_at", "")
            write_json(research_path, research)

        claims = []
        seen: set[str] = set()
        for item in _claimable(converted["locales"]["en"]):
            if item["block_id"] in seen:
                continue
            seen.add(item["block_id"])
            claims.append({
                "claim_id": f"claim-{item['block_id']}", "block_id": item["block_id"],
                "artifact": "Resume/index.html", "locale": "bilingual", "text": item["text"],
                "fact_ids": item["fact_ids"], "validation": "supported",
            })
        answer_path = evidence / "answer-plans.json"
        if answer_path.is_file():
            for question in read_json(answer_path).get("questions", []):
                question_id = str(question.get("question_id", ""))
                facts = list(question.get("fact_ids", []))
                if question_id and facts:
                    claims.append({
                        "claim_id": f"claim-{question_id}", "block_id": question_id,
                        "artifact": "Interview/interview-q-and-a.md", "locale": "en",
                        "text": str(question.get("reference_answer", "")), "fact_ids": facts,
                        "validation": "candidate-confirmation-required",
                    })
        write_json(evidence / "claim-ledger.json", {"schema_version": 1, "opportunity": reference, "claims": claims})
        walkthrough = (
            "# Legacy Output Upgrade Walkthrough\n\n"
            f"- Migration: `{migration_id}`\n- Opportunity: `{reference}`\n"
            "- Resume content: converted from generic schema v1 to fixed Method v1/schema v2.\n"
            "- Research records: provenance fields added without changing captured snapshots.\n"
            "- Resume claims: preserved with their candidate fact IDs.\n"
            "- Interview answers: marked `candidate-confirmation-required`; migration does not certify their semantics.\n"
            "- Legacy HTML/CSS/JavaScript/PDF files: moved into this backup before Method re-rendering.\n"
            "- PersonalWiki: not read or modified by this output-only conversion.\n"
        )
        write_text(backup / "walkthrough.md", walkthrough)
        write_json(backup / "manifest.json", {
            "migration_id": migration_id, "opportunity": reference, "created_at": utc_now(),
            "source_resume_hash": source_hash, "backup_files": sorted(path.name for path in backup.iterdir() if path.is_file()),
        })
        return {
            "opportunity": reference, "upgraded": True, "migration_id": migration_id,
            "backup": backup.relative_to(config.root).as_posix(),
            "walkthrough": (backup / "walkthrough.md").relative_to(config.root).as_posix(),
        }
