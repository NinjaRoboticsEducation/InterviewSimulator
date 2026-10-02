from __future__ import annotations

import re


def answer_spans(answer: str) -> dict[str, str]:
    """Stable exact substrings; punctuation and whitespace remain part of the source."""
    pieces = [m.group() for m in re.finditer(r"[^\n。！？!?]+[。！？!?]?|\n+", answer) if m.group().strip()]
    # Bound the selection table without duplicating all 6,000 answer characters.
    return {f"s{i + 1}": text[:240] for i, text in enumerate(pieces[:24])}


def compact_facts(snapshot: dict, questions: list, limit: int = 10) -> dict[str, str]:
    facts = {
        f["fact_id"]: f["statement"]
        for f in snapshot["inputs"]["candidate"]["facts"]
        if f.get("confidence") == "confirmed" and f.get("sensitive") is False
    }
    linked = [fid for q in questions for fid in q.fact_ids]
    matched = [
        fid
        for m in snapshot["inputs"].get("match_analysis", {}).get("matches", [])
        if m.get("status") in {"match", "partial"}
        for fid in m.get("fact_ids", [])
    ]
    ranked = dict.fromkeys([*linked, *matched, *facts])
    result: dict[str, str] = {}
    for fid in ranked:
        # Whole statements; omit oversized unrelated evidence instead of clipping meaning.
        if (
            fid in facts
            and (len(result) < limit or fid in linked)
            and (len(facts[fid]) <= 1800 or fid in linked)
        ):
            result[fid] = facts[fid]
    return result
