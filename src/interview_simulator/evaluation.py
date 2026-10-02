from __future__ import annotations

import json
import re
from typing import Any

DIMENSIONS = ("relevance", "specificity", "reasoning", "clarity", "reflection")
WEIGHTS = {
    "personal": (25, 25, 15, 20, 15),
    "professionalism": (20, 20, 25, 20, 15),
    "portfolio": (20, 30, 25, 15, 10),
    "role": (25, 10, 35, 20, 10),
    "company": (30, 10, 20, 20, 20),
}


def validate_evaluation(
    raw: dict[str, Any], answer: str, fact_ids: set[str], category: str, locale: str = "en"
) -> dict[str, Any]:
    if category not in WEIGHTS:
        raise ValueError("Unknown question category")
    scores = raw.get("scores")
    if not isinstance(scores, dict) or set(scores) != set(DIMENSIONS):
        raise ValueError("All five dimension scores are required")
    for dimension in DIMENSIONS:
        value = scores[dimension]
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError(f"Invalid {dimension} score")
    if not isinstance(raw.get("quote"), str) or not raw["quote"].strip() or raw["quote"] not in answer:
        raise ValueError("Evaluation quote must occur exactly in the confirmed answer")
    for field in ("strength", "improvement", "reason"):
        if not isinstance(raw.get(field), str) or not raw[field].strip() or len(raw[field]) > 3000:
            raise ValueError(f"Missing {field}")
    _normalize_feedback(raw, ("strength", "improvement", "reason"), locale)
    cited = raw.get("fact_ids", [])
    if (
        not isinstance(cited, list)
        or not all(isinstance(v, str) for v in cited)
        or not set(cited) <= fact_ids
    ):
        raise ValueError("Evaluation cites unknown PersonalWiki facts")
    result = {key: raw[key] for key in ("scores", "quote", "strength", "improvement", "reason")}
    result["fact_ids"] = cited
    result["score"] = round(
        sum(scores[d] * weight / 4 for d, weight in zip(DIMENSIONS, WEIGHTS[category])), 1
    )
    return result


def _normalize_feedback(raw: dict[str, Any], fields: tuple[str, ...], locale: str) -> None:
    from .localization import validate_text

    for field in fields:
        raw[field] = validate_text(raw[field], locale)


def skipped_evaluation(locale: str) -> dict[str, Any]:
    wording = {
        "en": (
            "No answer was given.",
            "Practice answering this question.",
            "The question was intentionally skipped.",
        ),
        "ja": (
            "回答はありません。",
            "この質問への回答を練習してください。",
            "この質問は意図的に省略されました。",
        ),
        "zh-Hant": ("未提供答案。", "請練習回答這個問題。", "此題已由候選人刻意略過。"),
    }[locale]
    return {
        "scores": {key: 0 for key in DIMENSIONS},
        "quote": "",
        "strength": wording[0],
        "improvement": wording[1],
        "reason": wording[2],
        "fact_ids": [],
        "score": 0.0,
        "skipped": True,
    }


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise TypeError("Model response must be a JSON object")
    return value


def validate_coaching(
    raw: dict[str, Any], known_facts: dict[str, str], question: dict[str, Any]
) -> dict[str, Any]:
    ids = raw.get("fact_ids")
    if (
        not isinstance(ids, list)
        or not all(isinstance(v, str) for v in ids)
        or not set(ids) <= known_facts.keys()
    ):
        raise ValueError("Coaching cites unknown candidate facts")
    for key in ("why_it_works", "outline", "next_action"):
        if not isinstance(raw.get(key), str) or not raw[key].strip() or len(raw[key]) > 3000:
            raise ValueError(f"Coaching is missing {key}")
    _normalize_feedback(raw, ("why_it_works", "outline", "next_action"), question["locale"])
    for field in ("why_it_works", "outline", "next_action"):
        if sum(name in raw[field] for name in ("why_it_works", "next_action", "example_parts")) >= 2:
            raise ValueError("Coaching repeated schema instructions instead of practical advice")
    # Legacy responses remain readable, but new tasks always use reviewed clauses.
    clauses = raw.get("example_clauses")
    if clauses is None:
        if question["locale"] != "en":
            raise ValueError("Legacy source-language examples need localized coaching")
        parts = raw.get("example_parts", [])
        if not isinstance(parts, list) or len(parts) > 4:
            raise ValueError("Coaching requires at most four evidence slots")
        slots = set()
        for part in parts:
            if (
                not isinstance(part, dict)
                or part.get("slot") not in {"situation", "action", "result", "reflection"}
                or part.get("fact_id") not in ids
                or part["slot"] in slots
            ):
                raise ValueError("Coaching slot must cite an approved fact exactly once")
            slots.add(part["slot"])
        example = " ".join(known_facts[fid] for fid in ids)
        example += " I would explain my own contribution clearly and verify any outcome before claiming it."
    else:
        from .localization import numeric_values, validate_text

        if not isinstance(clauses, list) or not 1 <= len(clauses) <= 5:
            raise ValueError("A finished example needs one to five supported clauses")
        texts = []
        for clause in clauses:
            if not isinstance(clause, dict) or set(clause) != {"text", "kind", "fact_ids"}:
                raise ValueError("Invalid example clause")
            references = clause["fact_ids"]
            if not isinstance(references, list) or not all(
                isinstance(i, str) and i in ids for i in references
            ):
                raise ValueError("Example clause cites unknown evidence")
            text = validate_text(clause["text"], question["locale"])
            if clause["kind"] == "fact":
                if not references:
                    raise ValueError("Career claims require profile evidence")
                source = " ".join(known_facts[i] for i in references)
                numbers = numeric_values(text)
                if not numbers <= numeric_values(source):
                    raise ValueError("Example introduced an unsupported metric or date")
            elif clause["kind"] == "prospective":
                markers = {
                    "en": r"\b(would|could|will|if|plan|intend)\b",
                    "ja": r"たい|場合|なら|考え|つもり|まず|予定|今後|将来",
                    "zh-Hant": r"會|如果|計畫|希望|首先|將|打算|未來",
                }
                if (
                    references
                    or not re.search(markers[question["locale"]], text, re.IGNORECASE)
                    or numeric_values(text)
                ):
                    raise ValueError("Future advice must be conditional and contain no invented metrics")
            else:
                raise ValueError("Unknown example clause kind")
            texts.append(text)
        example = " ".join(texts)
    return {
        "fact_ids": ids,
        "example": example,
        "why_it_works": raw["why_it_works"],
        "outline": raw["outline"],
        "next_action": raw["next_action"],
        **({"example_clauses": clauses} if clauses is not None else {}),
    }
