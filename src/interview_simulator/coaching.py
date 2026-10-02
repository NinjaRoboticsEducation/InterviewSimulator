"""Evidence selection and the mandatory example contract, shared by both interfaces."""

from __future__ import annotations

import re
from typing import Any

CONTRACT_VERSION = 4
KINDS = ("fact", "company", "prospective", "motivation", "question", "bridge")


class CoachingValidationError(ValueError):
    def __init__(self, code: str, clause: int | None = None):
        self.code, self.clause = code, clause
        super().__init__(code)


def has_example(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and all(
            isinstance(value.get(k), str) and bool(value[k].strip())
            for k in ("example", "why_it_works", "outline", "next_action")
        )
        and isinstance(value.get("fact_ids"), list)
    )


def example_count(run: dict) -> int:
    return sum(has_example(e.get("coaching")) for e in run["evaluations"].values())


def evidence_packet(snapshot: dict, question: dict, facts: dict[str, str]) -> tuple[dict, dict]:
    """Bound context using question links, compatibility matches, then lexical relevance."""
    requirements = snapshot["inputs"]["requirements"].get("requirements", [])
    selected_requirements = [r for r in requirements if r["requirement_id"] in question["requirement_ids"]]
    tokens = set(re.findall(r"\w+", question["text"].casefold()))
    linked = list(question["fact_ids"])
    for match in snapshot["inputs"].get("match_analysis", {}).get("matches", []):
        if match.get("requirement_id") in question["requirement_ids"] and match.get("status") in {
            "match",
            "partial",
        }:
            linked.extend(match.get("fact_ids", []))
    ranked = sorted(
        facts, key=lambda fid: (-len(tokens & set(re.findall(r"\w+", facts[fid].casefold()))), fid)
    )
    ids = list(dict.fromkeys([*linked, *ranked]))[:4]
    candidate = {fid: facts[fid] for fid in ids if fid in facts}
    company = {"requirement:" + r["requirement_id"]: r["statement"] for r in selected_requirements[:3]}
    sources = snapshot["inputs"].get("research", {}).get("sources", [])
    sources = sorted(sources, key=lambda s: s.get("source_id") not in question.get("source_ids", []))
    for source in sources:
        if len(company) >= 6:
            break
        if (
            source.get("source_tier") in {"official", "primary"}
            and source.get("claim_type") == "direct"
            and source.get("source_id")
            and source.get("excerpt")
        ):
            company["company:" + source["source_id"]] = source["excerpt"]
    return candidate, {**question, "company_evidence": company, "coaching_contract": CONTRACT_VERSION}
