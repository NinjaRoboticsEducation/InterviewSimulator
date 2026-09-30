from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from interviewwiki.config import Config
from interviewwiki.service import InterviewWikiService
from interviewwiki.util import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "portable-interviewwiki"
    root.mkdir()
    shutil.copy2(PROJECT_ROOT / "interviewwiki.yaml", root / "interviewwiki.yaml")
    shutil.copytree(PROJECT_ROOT / "schemas", root / "schemas")
    shutil.copytree(PROJECT_ROOT / "templates", root / "templates")
    (root / "PersonalWiki/wiki").mkdir(parents=True)
    (root / "PersonalWiki/raw/notes").mkdir(parents=True)
    (root / "PersonalWiki/raw/_catalog").mkdir(parents=True)

    source = root / "PersonalWiki/raw/notes/candidate-source.md"
    source.write_text(
        "Fictional fixture: led a delivery that improved throughput by 25 percent.\n"
        "Fictional fixture: uses Python for data tooling.\n",
        encoding="utf-8",
    )
    digest = sha256_file(source)
    record = {
        "id": "src-candidate-fixture",
        "path": "raw/notes/candidate-source.md",
        "media_type": "text/markdown",
        "title": "Candidate fixture",
        "added_at": "2026-01-01T00:00:00Z",
        "content_hash": digest,
        "state": "ingested",
    }
    (root / "PersonalWiki/raw/_catalog/src-candidate-fixture.yaml").write_text(
        yaml.safe_dump(record, sort_keys=False), encoding="utf-8"
    )
    (root / "PersonalWiki/wiki/candidate.md").write_text(
        "---\n"
        "type: Entity\n"
        "title: Fictional Candidate\n"
        "sources:\n"
        "  - id: src-candidate-fixture\n"
        f"    content_hash: {digest}\n"
        "candidate_facts:\n"
        "  - fact_id: fact-delivery-improvement\n"
        "    kind: achievement\n"
        "    statement: Led a delivery that improved throughput by 25 percent.\n"
        "    source_ids: [src-candidate-fixture]\n"
        "    confidence: confirmed\n"
        "  - fact_id: fact-python-tooling\n"
        "    kind: skill\n"
        "    statement: Uses Python for data tooling.\n"
        "    source_ids: [src-candidate-fixture]\n"
        "    confidence: confirmed\n"
        "---\n\n"
        "# Fictional Candidate\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def prepared(project: Path) -> tuple[Path, InterviewWikiService, str]:
    service = InterviewWikiService(project)
    service.initialize()
    reference = service.opportunity_create("Example Company", "Platform Engineer")
    source = project / "JobDescriptions/example-company/platform-engineer/sources/job.md"
    source.write_text(
        "# Platform Engineer\n\nBuild reliable services using Python and communicate delivery outcomes.\n",
        encoding="utf-8",
    )
    service.run_prepare(reference)
    populate_valid_artifacts(Config.load(project), reference)
    return project, service, reference


def populate_valid_artifacts(config: Config, reference: str) -> None:
    output = config.output / reference
    evidence = output / "Evidence"
    source_records = json.loads((evidence / "opportunity-sources.json").read_text(encoding="utf-8"))
    opportunity_source = source_records["sources"][0]["source_id"]
    fact_delivery = "fact-delivery-improvement"
    fact_python = "fact-python-tooling"

    write_json(
        evidence / "requirements.json",
        {
            "schema_version": 1,
            "opportunity": reference,
            "requirements": [
                {
                    "requirement_id": "req-python-services",
                    "category": "required",
                    "priority": "critical",
                    "statement": "Build reliable services using Python.",
                    "evidence": [{"source_id": opportunity_source, "quote": "using Python"}],
                }
            ],
        },
    )
    write_json(
        evidence / "match-analysis.json",
        {
            "schema_version": 1,
            "opportunity": reference,
            "matches": [
                {
                    "requirement_id": "req-python-services",
                    "status": "match",
                    "fact_ids": [fact_python],
                    "analysis": "The confirmed Python tooling fact supports this requirement.",
                }
            ],
            "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
            "recruiter_concerns": [],
            "preparation_strategy": [],
        },
    )
    questions = []
    for index in range(1, 6):
        questions.append(
            {
                "question_id": f"q-example-{index}",
                "category": "behavioral",
                "question": f"Fixture question {index}?",
                "fact_ids": [fact_delivery],
                "requirement_ids": ["req-python-services"],
                "reference_answer": "Use the confirmed delivery example and do not add new metrics.",
            }
        )
    write_json(
        evidence / "answer-plans.json",
        {"schema_version": 1, "opportunity": reference, "questions": questions},
    )
    def method_locale(ja: bool) -> dict[str, Any]:
        prefix = "ja" if ja else "en"
        labels = {
            "self_introduction": "自己紹介" if ja else "Self Introduction",
            "professional_experience": "職務経歴" if ja else "Professional Experience",
            "responsibilities": "担当業務" if ja else "Responsibilities",
            "achievements": "主な実績" if ja else "Key Achievements",
            "earlier_career": "その他の職務経歴" if ja else "Earlier Career",
            "earlier_headers": ["期間", "職位", "会社", "勤務地"] if ja else ["Period", "Title", "Company", "Location"],
            "expertise": "個人の専門領域" if ja else "Personal Expertise",
            "self_pr": "自己PR" if ja else "Self PR",
        }
        sidebar_labels = {
            "contact": "連絡先" if ja else "Contact", "languages": "言語" if ja else "Languages",
            "skills": "専門領域" if ja else "Skills", "tools": "ツール" if ja else "Tools",
            "education": "学歴" if ja else "Education", "awards": "受賞歴" if ja else "Awards",
        }
        return {
            "name": "架空の候補者" if ja else "Fictional Candidate",
            "headline": "プラットフォームエンジニア" if ja else "Platform Engineer",
            "sidebar": {
                "labels": sidebar_labels,
                "languages": [{"block_id": "language-example", "language": "英語" if ja else "English", "level": "業務レベル" if ja else "Professional", "fact_ids": [fact_python]}],
                "skills": [{"block_id": "skill-python", "text": "Pythonツール" if ja else "Python tooling", "fact_ids": [fact_python]}],
                "tools": [{"block_id": "tool-python", "text": "Python", "fact_ids": [fact_python]}],
                "education": [{"block_id": "education-example", "institution": "架空大学" if ja else "Example University", "detail": "工学" if ja else "Engineering", "period": "", "fact_ids": [fact_python]}],
                "awards": [],
            },
            "section_labels": labels,
            "self_introduction": [
                {"block_id": "intro-summary", "text": "Pythonツールの実務経験。" if ja else "Python tooling practitioner.", "fact_ids": [fact_python]},
                {"block_id": "intro-delivery", "text": "改善を実行し検証します。" if ja else "Builds and validates delivery improvements.", "fact_ids": [fact_delivery]},
            ],
            "signals": [
                {"block_id": f"signal-{index}", "label": ("強み" if ja else "Signal") + " " + word, "text": "デリバリー改善" if ja else "Delivery improvement", "fact_ids": [fact_delivery]}
                for index, word in enumerate(("One", "Two", "Three", "Four"), 1)
            ],
            "professional_experience": [{
                "block_id": "experience-example", "company": "架空会社" if ja else "Example Company",
                "role": "デリバリーリード" if ja else "Delivery Lead", "period": "Present", "location": "",
                "fact_ids": [fact_delivery],
                "responsibilities": [
                    {"block_id": "responsibility-delivery", "text": "改善施策を主導。" if ja else "Led a delivery improvement.", "fact_ids": [fact_delivery]},
                    {"block_id": "responsibility-validation", "text": "デリバリーワークフローの変更を構築し検証。" if ja else "Built and validated changes to the delivery workflow.", "fact_ids": [fact_delivery]},
                ],
                "achievements": [
                    {"block_id": "achievement-throughput", "text": "スループットを25パーセント改善。" if ja else "Improved throughput by 25 percent.", "fact_ids": [fact_delivery]},
                    {"block_id": "achievement-workflow", "text": "確認済みのワークフロー改善を実現。" if ja else "Delivered a confirmed workflow improvement.", "fact_ids": [fact_delivery]},
                ],
            }],
            "earlier_career": [],
            "expertise": [
                {"block_id": f"expertise-{index}", "title": ("専門性" if ja else "Expertise") + " " + word, "fact_ids": [fact_python],
                 "bullets": [{"block_id": f"expertise-{index}-detail", "text": "Pythonツール" if ja else "Python tooling", "fact_ids": [fact_python]}]}
                for index, word in enumerate(("One", "Two", "Three", "Four"), 1)
            ],
            "self_pr": [
                {"block_id": "self-pr-summary", "text": "改善を実行し検証します。" if ja else "Builds, validates, and improves delivery workflows.", "fact_ids": [fact_delivery]},
                {"block_id": "self-pr-contribution", "text": "Pythonの経験を活かして貢献したいと考えています。" if ja else "Would welcome the opportunity to contribute practical Python experience.", "fact_ids": [fact_python]},
            ],
        }

    en_locale = method_locale(False)
    ja_locale = method_locale(True)
    write_json(
        evidence / "resume-content.json",
        {
            "schema_version": 2,
            "template_id": "method-v1",
            "opportunity": reference,
            "candidate": {
                "email": "candidate@example.test",
                "phone": "",
                "website": "",
                "location": "",
                "consent_to_publish": True,
            },
            "locales": {"en": en_locale, "ja": ja_locale},
        },
    )
    claims = []
    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("block_id") and value.get("fact_ids"):
                block_id = value["block_id"]
                text = " ".join(str(value.get(key, "")) for key in ("text", "label", "language", "level", "institution", "detail", "period", "year", "company", "role", "title")).strip()
                claims.append({"claim_id": f"claim-{block_id}", "block_id": block_id, "artifact": "Resume/index.html", "locale": "bilingual", "text": text or block_id, "fact_ids": value["fact_ids"], "validation": "supported"})
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(en_locale)
    for question in questions:
        claims.append({"claim_id": f"claim-{question['question_id']}", "block_id": question["question_id"], "artifact": "Interview/interview-q-and-a.md", "locale": "en", "text": question["reference_answer"], "fact_ids": question["fact_ids"], "validation": "supported"})
    write_json(
        evidence / "claim-ledger.json",
        {
            "schema_version": 1,
            "opportunity": reference,
            "claims": claims,
        },
    )
    (output / "Interview/candidate-analysis.md").write_text(
        "# Candidate Analysis\n\nGrounded in `fact-python-tooling`.\n", encoding="utf-8"
    )
    (output / "Interview/interview-q-and-a.md").write_text(
        "# Interview Q&A\n\nAnswers use `fact-delivery-improvement`.\n", encoding="utf-8"
    )
