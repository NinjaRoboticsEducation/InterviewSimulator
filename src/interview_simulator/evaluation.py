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
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ValueError(f"Missing {field}")
    _normalize_feedback(raw, ("strength", "improvement", "reason"), locale)
    cited = raw.get("fact_ids", [])
    if not isinstance(cited, list) or not set(cited) <= fact_ids:
        raise ValueError("Evaluation cites unknown PersonalWiki facts")
    result = {key: raw[key] for key in ("scores", "quote", "strength", "improvement", "reason")}
    result["fact_ids"] = cited
    result["score"] = round(
        sum(scores[d] * weight / 4 for d, weight in zip(DIMENSIONS, WEIGHTS[category])), 1
    )
    return result


def _normalize_feedback(raw: dict[str, Any], fields: tuple[str, ...], locale: str) -> None:
    if locale == "ja":
        for field in fields:
            if not re.search(r"[\u3040-\u30ff]", raw[field]):
                raise ValueError(f"{field} must be written in Japanese, not English")
    elif locale == "zh-Hant":
        from opencc import OpenCC

        converter = OpenCC("s2twp")
        for field in fields:
            raw[field] = converter.convert(raw[field])
            if not re.search(r"[\u3400-\u9fff]", raw[field]):
                raise ValueError(f"{field} must be written in Traditional Chinese")


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
    if not isinstance(ids, list) or not set(ids) <= known_facts.keys():
        raise ValueError("Coaching cites unknown candidate facts")
    for key in ("why_it_works", "outline", "next_action"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"Coaching is missing {key}")
    _normalize_feedback(raw, ("why_it_works", "outline", "next_action"), question["locale"])
    # Candidate-specific prose is assembled from exact approved fact statements. A
    # model-generated sample cannot be fact-checked reliably by a shape validator.
    facts = " ".join(known_facts[fid] for fid in ids) or "[add a confirmed profile example]"
    templates = {
        "en": {
            "personal": f"My relevant background includes: {facts} I would apply this experience to the role by [add a specific, verified contribution].",
            "professionalism": f"A relevant part of my background is: {facts} In a similar situation I would [add a concrete action and reason].",
            "portfolio": f"One relevant work example is: {facts} My own action was [add a verified action]. The result was [add a verified result].",
            "role": f"My relevant experience includes: {facts} For this requirement, I would start by [explain a realistic approach and trade-off].",
            "company": f"My interest in this role comes from [add a verified company-specific reason]. My relevant background includes: {facts}",
        },
        "ja": {
            "personal": f"関連する確認済みの経歴：{facts} この経験を職務で［確認できる具体的な貢献］に生かしたいです。",
            "professionalism": f"関連する確認済みの経歴：{facts} 同様の状況では［具体的な行動と理由］を説明します。",
            "portfolio": f"関連する仕事の事例：{facts} 自分が行ったことは［確認できる行動］で、結果は［確認できる成果］でした。",
            "role": f"関連する確認済みの経歴：{facts} この要件には［現実的な進め方とトレードオフ］から取り組みます。",
            "company": f"この職務に関心を持つ理由は［確認できる企業固有の理由］です。関連する経歴：{facts}",
        },
        "zh-Hant": {
            "personal": f"我相關且已確認的背景包括：{facts} 我會把這些經驗用於［可查證的具體貢獻］。",
            "professionalism": f"相關且已確認的背景：{facts} 遇到類似情況，我會［說明具體行動及原因］。",
            "portfolio": f"一個相關的工作案例是：{facts} 我個人的行動是［可查證的行動］，成果是［可查證的結果］。",
            "role": f"相關且已確認的經驗：{facts} 面對這項要求，我會先［說明可行方法及取捨］。",
            "company": f"我對這個職位感興趣，因為［可查證的公司相關原因］。我的相關背景包括：{facts}",
        },
    }
    locale = question["locale"]
    category = question["category"]
    if locale not in templates or category not in templates[locale]:
        raise ValueError("Unsupported coaching language")
    guidance = {
        "en": (
            "This example uses confirmed profile facts and marks missing details for you to verify.",
            "Give context, explain your own action, state a verified result, then reflect.",
            "Replace each bracketed prompt with a detail you can verify, then practise aloud.",
        ),
        "ja": (
            "確認済みの経歴だけを使い、不足する情報は確認事項として示しています。",
            "状況、自分の行動、確認できる成果、振り返りの順で説明してください。",
            "角括弧の部分を確認できる内容で補い、声に出して練習してください。",
        ),
        "zh-Hant": (
            "此範例只使用已確認的個人經歷，並標示需要查證的細節。",
            "依序說明背景、自己的行動、可查證的成果，以及反思。",
            "以可查證的細節補上括號中的提示，再開口練習。",
        ),
    }[locale]
    return {
        "fact_ids": ids,
        "example": templates[locale][category],
        "why_it_works": guidance[0],
        "outline": guidance[1],
        "next_action": guidance[2],
    }
