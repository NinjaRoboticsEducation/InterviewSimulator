from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

CATEGORIES = ("personal", "professionalism", "portfolio", "role", "company")
LOCALES = ("en", "ja", "zh-Hant")

PROMPTS = {
    "en": (
        "Please introduce yourself and explain how your background connects to the {role} role.",
        "Which part of your experience best prepares you for this opportunity, and why?",
        "Tell me about a time you had to prioritize competing work. What did you do?",
        "Describe a difficult professional conversation and how you handled it.",
        "Walk me through a project you are proud of. What did you personally contribute?",
        "Choose a work example and explain your decisions, result, and what you would improve.",
        "How would you approach this requirement: {requirement}?",
        "What trade-offs would you consider when delivering this role's most important work?",
        "Why do you want to work at {company} in this {role} position?",
        "What would you want to learn about {company} before accepting this role?",
    ),
    "ja": (
        "自己紹介をお願いします。これまでの経験は{role}の仕事にどうつながりますか。",
        "この機会に最も役立つ経験は何ですか。その理由も教えてください。",
        "複数の仕事の優先順位を決めた経験を教えてください。どう対応しましたか。",
        "難しい仕事上の対話をどのように進めたか、具体例を教えてください。",
        "誇りに思うプロジェクトを説明してください。ご自身の貢献は何でしたか。",
        "仕事の事例を一つ選び、判断、結果、改善できる点を説明してください。",
        "次の要件にどう取り組みますか：{requirement}。",
        "この職務の重要な仕事を進める際、どのようなトレードオフを考えますか。",
        "なぜ{company}の{role}の職務を志望しますか。",
        "この職務を受ける前に、{company}について何を確認したいですか。",
    ),
    "zh-Hant": (
        "請先自我介紹，並說明你的背景如何符合{role}職位。",
        "你哪一段經驗最能幫助你勝任這個機會？為什麼？",
        "請分享一次你需要安排多項工作優先順序的經驗。你如何處理？",
        "請描述一次困難的職場溝通，以及你如何應對。",
        "請介紹一個令你自豪的專案。你個人的貢獻是什麼？",
        "請選一個工作案例，說明你的判斷、成果和可以改進之處。",
        "你會如何處理這項職位要求：{requirement}？",
        "執行這個職位最重要的工作時，你會考慮哪些取捨？",
        "你為什麼想擔任{company}的{role}職位？",
        "接受這個職位之前，你會想進一步了解{company}哪些事情？",
    ),
}

EVIDENCE_PROMPTS = {
    "en": {
        1: "Your profile includes this experience: “{fact}” How does it prepare you for this role?",
        4: "Your profile includes this work example: “{fact}” What did you personally do, and what was the result?",
        5: "Looking again at “{fact}”, what decisions did you make and what would you improve?",
        8: "A company source describes this priority: “{research}” Why does this work at {company} interest you?",
        9: "What would you ask {company} about this published priority: “{research}”?",
    },
    "ja": {
        1: "プロフィールには「{fact}」とあります。この経験は今回の職務にどう役立ちますか。",
        4: "プロフィールにある事例「{fact}」について、ご自身が行ったことと結果を教えてください。",
        5: "「{fact}」について、どのような判断をし、何を改善したいですか。",
        8: "企業資料には「{research}」とあります。{company}のこの仕事に関心を持つ理由は何ですか。",
        9: "公開資料にある「{research}」について、{company}に何を質問したいですか。",
    },
    "zh-Hant": {
        1: "你的個人資料提到「{fact}」。這段經驗如何幫助你勝任這個職位？",
        4: "你的個人資料提到「{fact}」。你個人的行動及成果是什麼？",
        5: "關於「{fact}」，你當時如何作決定？現在會改進什麼？",
        8: "公司資料提到「{research}」。為什麼你對{company}的這項工作有興趣？",
        9: "對於公開資料中的「{research}」，你會向{company}提出什麼問題？",
    },
}


def _excerpt(value: object, limit: int = 220) -> str:
    words = " ".join(str(value).split())
    return words[:limit].rstrip() + ("…" if len(words) > limit else "")


@dataclass(frozen=True)
class Question:
    question_id: str
    category: str
    text: str
    locale: str
    fact_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    source_question_id: str | None = None
    source_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_questions(
    questions: list[Question], facts: set[str], requirements: set[str], sources: set[str] | None = None
) -> None:
    if len(questions) != 10 or Counter(q.category for q in questions) != {name: 2 for name in CATEGORIES}:
        raise ValueError("Exactly ten scored questions with two in each category are required")
    if len({q.question_id for q in questions}) != 10 or len({q.text.strip() for q in questions}) != 10:
        raise ValueError("Question IDs and wording must be unique within the run")
    for q in questions:
        if q.locale not in LOCALES or not q.text.strip():
            raise ValueError("Invalid locale or empty question")
        if not set(q.fact_ids) <= facts or not set(q.requirement_ids) <= requirements:
            raise ValueError("Question references unknown evidence")
        if sources is not None and not set(q.source_ids) <= sources:
            raise ValueError("Question references unknown company source")


def make_fixed_questions(snapshot: dict[str, Any], locale: str) -> list[Question]:
    """A safe baseline sequence. Prepared evidence shapes the role/company wording."""
    if locale not in LOCALES:
        raise ValueError("Unsupported interview language")
    facts = [
        f
        for f in snapshot["inputs"]["candidate"].get("facts", [])
        if f.get("confidence") == "confirmed" and f.get("sensitive") is False
    ]
    requirements = snapshot["inputs"]["requirements"].get("requirements", [])
    all_fact_ids = tuple(str(f["fact_id"]) for f in facts)
    req_ids = tuple(str(r["requirement_id"]) for r in requirements)
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    priority = {
        str(r["requirement_id"]): (ranks.get(str(r.get("priority")), 4), index)
        for index, r in enumerate(requirements)
    }
    matched = sorted(
        snapshot["inputs"].get("match_analysis", {}).get("matches", []),
        key=lambda item: priority.get(str(item.get("requirement_id")), (5, len(requirements))),
    )
    relevant = [
        str(fid)
        for item in matched
        if item.get("status") in {"match", "partial"}
        for fid in item.get("fact_ids", [])
        if str(fid) in all_fact_ids
    ]
    fact_ids = tuple(dict.fromkeys([*relevant, *all_fact_ids]))
    research = snapshot["inputs"].get("research", {}).get("sources", [])
    trusted_research = [
        item
        for item in research
        if item.get("source_tier") in {"official", "primary"}
        and item.get("claim_type") == "direct"
        and item.get("source_id")
        and str(item.get("excerpt", "")).strip()
    ]
    source_ids = {str(item["source_id"]) for item in research if item.get("source_id")}
    if not fact_ids or not req_ids:
        raise ValueError("Confirmed facts and role requirements are needed")
    chosen = min(requirements, key=lambda r: ranks.get(str(r.get("priority")), 4))
    result = []
    for index, template in enumerate(PROMPTS[locale]):
        category = CATEGORIES[index // 2]
        text = template.format(
            role=snapshot["role"], company=snapshot["company"], requirement=chosen["statement"]
        )
        fact_position = index if category == "personal" else index - 4
        bound_facts = (
            (fact_ids[fact_position % len(fact_ids)],) if category in {"personal", "portfolio"} else ()
        )
        bound_reqs = (str(chosen["requirement_id"]),) if category in {"role", "company"} else ()
        bound_sources: tuple[str, ...] = ()
        if index in {1, 4, 5}:
            fact_id = fact_ids[fact_position % len(fact_ids)]
            fact = next(item["statement"] for item in facts if item["fact_id"] == fact_id)
            text = EVIDENCE_PROMPTS[locale][index].format(fact=_excerpt(fact))
        elif index in {8, 9} and trusted_research:
            source = trusted_research[(index - 8) % len(trusted_research)]
            bound_sources = (str(source["source_id"]),)
            text = EVIDENCE_PROMPTS[locale][index].format(
                company=snapshot["company"], research=_excerpt(source["excerpt"])
            )
        result.append(
            Question(
                f"q-{index + 1:02d}",
                category,
                text,
                locale,
                bound_facts,
                bound_reqs,
                source_ids=bound_sources,
            )
        )
    if locale == "en":
        category_map = {
            "introduction": "personal",
            "behavioral": "professionalism",
            "leadership": "professionalism",
            "portfolio": "portfolio",
            "technical": "role",
            "role-specific": "role",
            "motivation": "company",
            "candidate-question": "company",
        }
        used_slots: set[int] = set()
        for prepared in snapshot["inputs"].get("answer_plans", {}).get("questions", []):
            mapped_category = category_map.get(prepared.get("category"))
            if not mapped_category:
                continue
            fact_refs = tuple(prepared.get("fact_ids", []))
            req_refs = tuple(prepared.get("requirement_ids", []))
            wording = str(prepared.get("question", "")).strip()
            if not wording or not set(fact_refs) <= set(fact_ids) or not set(req_refs) <= set(req_ids):
                continue
            slot = next(
                (i for i, q in enumerate(result) if q.category == mapped_category and i not in used_slots),
                None,
            )
            if slot is None:
                continue
            if any(wording == q.text for i, q in enumerate(result) if i != slot):
                continue
            result[slot] = Question(
                result[slot].question_id,
                mapped_category,
                wording,
                locale,
                fact_refs,
                req_refs,
                str(prepared.get("question_id")),
            )
            used_slots.add(slot)
    validate_questions(result, set(fact_ids), set(req_ids), source_ids)
    return result
