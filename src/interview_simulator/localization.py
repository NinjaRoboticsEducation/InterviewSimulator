"""Versioned display translations; original wiki evidence is never overwritten."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

from .files import reject_links
from .providers.credentials import save_private_json
from .questions import validate_questions

VERSION = "question-localization-v1"
GLOSSARY = {"GTM": "go-to-market", "ROI": "return on investment", "APAC": "Asia Pacific"}


def numeric_values(text: str) -> set[str]:
    """Compare explicit quantities across common English and CJK written forms."""
    text = unicodedata.normalize("NFKC", text).lower()
    words = dict(
        zip(
            [
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
                "ten",
                "eleven",
                "twelve",
                "thirteen",
                "fourteen",
                "fifteen",
                "sixteen",
                "seventeen",
                "eighteen",
                "nineteen",
                "twenty",
            ],
            range(21),
        )
    )
    for word, value in words.items():
        text = re.sub(r"\b" + word + r"\b", str(value), text)
    digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "兩": 2, "两": 2})
    units = {"十": 10, "百": 100, "千": 1000}

    def cjk_number(match: re.Match[str]) -> str:
        total, current = 0, 0
        for char in match[0]:
            if char in units:
                total += (current or 1) * units[char]
                current = 0
            else:
                current = current * 10 + digits[char]
        return str(total + current)

    # A number must be used as a quantity, not part of a word such as 一般 (general).
    text = re.sub(
        r"[零〇一二三四五六七八九兩两十百千]+(?=[つ個件人年月日回項本社冊%％]|\s|$)",
        cjk_number,
        text,
    )
    return set(re.findall(r"\d+(?:[.,]\d+)*%?", text))


def validate_text(value: object, locale: str, original: str = "", protected: tuple[str, ...] = ()) -> str:
    if not isinstance(value, str):
        raise TypeError("Language output must be text")
    text: str = value
    if not 3 <= len(text.strip()) <= 3000:
        raise ValueError("Language output must be complete bounded text")
    if re.search(
        r"```|<think>|\[(?:add|insert|TODO)|［|example_parts|quote_span_id|confirmed_facts|repair_error",
        text,
        re.IGNORECASE,
    ):
        raise ValueError("Language output contains placeholders or model instructions")
    if locale == "zh-Hant":
        from opencc import OpenCC

        text = OpenCC("s2twp").convert(text)
    if locale == "ja" and not re.search(r"[\u3040-\u30ff]", text):
        raise ValueError("Output must be Japanese")
    if locale == "zh-Hant" and not re.search(r"[\u3400-\u9fff]", text):
        raise ValueError("Output must be Traditional Chinese")
    if locale != "en":
        remainder = text
        for name in protected:
            if name:
                remainder = remainder.replace(name, "")
        if re.search(r"[A-Za-z]+(?:\s+[A-Za-z]+){3,}", remainder):
            raise ValueError("Output contains an untranslated English passage")
    if original and numeric_values(text) != numeric_values(original):
        raise ValueError("Translation changed a number")
    return text.strip()


class Localizer:
    def __init__(self, root: Path, model, invoke):
        self.root, self.model, self.invoke = root / "translation-cache", model, invoke

    async def questions(self, snapshot: dict, questions: list) -> list:
        result = []
        identity = None
        for q in questions:
            # A cached or bank question already has frozen, validated display text.
            if q.localization_version == VERSION:
                result.append(q)
                continue
            protected = (snapshot["company"], *GLOSSARY)
            text = q.text
            native = q.locale == "en" or not re.search(r"[A-Za-z]{3,}", text.replace(snapshot["company"], ""))
            if not native:
                if identity is None:
                    identity = await self.model._identity("localization")
                evidence = {
                    f["fact_id"]: f["statement"]
                    for f in snapshot["inputs"]["candidate"]["facts"]
                    if f["fact_id"] in q.fact_ids
                    and f.get("confidence") == "confirmed"
                    and f.get("sensitive") is False
                }
                payload = {
                    "question": text,
                    "category": q.category,
                    "locale": q.locale,
                    "evidence": evidence,
                    "protected_names": list(protected),
                    "glossary": GLOSSARY,
                }
                digest = hashlib.sha256(
                    json.dumps([VERSION, identity, payload], sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
                path = self.root / (digest + ".json")
                reject_links(path)
                if path.exists():
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    text = validate_text(cached["text"], q.locale, q.text, protected)
                else:
                    text = await self.invoke(self.model.localize, payload)
                    text = validate_text(text, q.locale, q.text, protected)
                    save_private_json(path, {"version": VERSION, "text": text})
            text = validate_text(text, q.locale, protected=protected)
            result.append(
                replace(q, text=text, original_text=q.original_text or q.text, localization_version=VERSION)
            )
        validate_questions(
            result,
            {f["fact_id"] for f in snapshot["inputs"]["candidate"]["facts"]},
            {r["requirement_id"] for r in snapshot["inputs"]["requirements"]["requirements"]},
            {
                s["source_id"]
                for s in snapshot["inputs"].get("research", {}).get("sources", [])
                if "source_id" in s
            },
        )
        snapshot["localization"] = {"version": VERSION, "model": identity or {"source": "native-validated"}}
        return result
