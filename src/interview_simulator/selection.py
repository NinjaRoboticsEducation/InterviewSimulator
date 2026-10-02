"""Deterministic, bounded question-bank selection for a single interview turn."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

POLICY_VERSION = "bounded-bank-v2-cjk"


def tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = set(re.findall(r"[a-z0-9_]+", normalized))
    for phrase in re.findall(r"[\u3040-\u30ff\u3400-\u9fff]+", normalized):
        terms.update(phrase[i : i + 2] for i in range(len(phrase) - 1))
    return terms


def choose(run: dict[str, Any], ordinal: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep the fixed interview's category at each slot and select a current-evidence variant."""
    fixed = run["questions"][ordinal - 1]
    previous = run["answers"][-1]
    answer = previous["text"] if not previous["skipped"] else ""
    used = {question["text"] for question in run["questions"][: ordinal - 1]}
    future = {question["text"] for question in run["questions"][ordinal:]}
    eligible_facts = {
        f["fact_id"]
        for f in run["snapshot"]["inputs"]["candidate"]["facts"]
        if f.get("confidence") == "confirmed" and f.get("sensitive") is False
    }
    eligible_reqs = {r["requirement_id"] for r in run["snapshot"]["inputs"]["requirements"]["requirements"]}
    eligible_sources = {
        s["source_id"] for s in run["snapshot"]["inputs"].get("research", {}).get("sources", [])
    }
    pool = [fixed, *run["snapshot"].get("selection_pool", [])]
    candidates = []
    for candidate in pool[:21]:
        if (
            candidate["category"] != fixed["category"]
            or candidate["locale"] != run["locale"]
            or candidate["text"] in used
            or candidate["text"] in future
            or not set(candidate.get("fact_ids", [])) <= eligible_facts
            or not set(candidate.get("requirement_ids", [])) <= eligible_reqs
            or not set(candidate.get("source_ids", [])) <= eligible_sources
        ):
            continue
        candidates.append(candidate)
    answer_tokens = tokens(answer)

    def rank(question: dict[str, Any]) -> tuple[int, int, str]:
        overlap = len(answer_tokens & tokens(question["text"]))
        # The fixed question wins ties, so sparse banks never disrupt the baseline.
        return (-overlap, 0 if question["text"] == fixed["text"] else 1, question["text"])

    winner = min(candidates, key=rank) if candidates else fixed
    chosen = {**winner, "question_id": fixed["question_id"]}
    decision = {
        "policy_version": POLICY_VERSION,
        "ordinal": ordinal,
        "answer_sha256": "sha256:" + hashlib.sha256(answer.encode()).hexdigest(),
        "candidate_count": len(candidates),
        "selected_text_sha256": "sha256:" + hashlib.sha256(chosen["text"].encode()).hexdigest(),
        "fallback": chosen["text"] == fixed["text"],
        "reason": "answer word/CJK bigram overlap within the required topic; fixed question wins ties",
    }
    return chosen, decision
