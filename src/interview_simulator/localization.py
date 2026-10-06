"""Versioned display translations; original wiki evidence is never overwritten."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import replace
from pathlib import Path

from .files import reject_links
from .providers.credentials import save_private_json
from .questions import validate_questions

VERSION = "question-localization-v2"
GLOSSARY = {"GTM": "go-to-market", "ROI": "return on investment", "APAC": "Asia Pacific"}


class LocalizationValidationError(ValueError):
    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.ordinal: int | None = None
        super().__init__(message)


_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_MONTH_PATTERN = "|".join(
    sorted(
        {word for month in _MONTHS for word in (month, month[:3], "Sept" if month == "September" else month)},
        key=len,
        reverse=True,
    )
)


def _named_dates(text: str) -> str:
    """Normalize explicit English calendar dates; do not convert names such as May alone."""
    months = {word.lower(): index for index, month in enumerate(_MONTHS, 1) for word in (month, month[:3])}
    months["sept"] = 9

    def canonical(match: re.Match[str]) -> str:
        year, month, day = match["year"], months[match["month"].lower()], match["day"]
        return f"{year}年{month}月" + (f"{int(day)}日" if day else "")

    # Day-first must run before month/year, or '5 August 2020' loses its day association.
    for pattern in (
        rf"(?<![\w])(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH_PATTERN})\.?\s+(?P<year>\d{{4}})(?!\d)",
        rf"\b(?P<month>{_MONTH_PATTERN})\.?\s+(?:(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+)?(?P<year>\d{{4}})(?!\d)",
    ):
        text = re.sub(pattern, canonical, text, flags=re.IGNORECASE)
    return text


def calendar_dates(text: str) -> Counter:
    """Keep year/month/day associations, not just an unordered set of numbers."""
    text = _numeric_text(text)
    dates = []
    for match in re.finditer(
        r"(?<!\d)(\d{4})(?:\s*年\s*|[-/])(\d{1,2})(?:\s*月(?:\s*(\d{1,2})\s*日)?|(?:[-/](\d{1,2}))?(?!\d))",
        text,
    ):
        year, month, day, iso_day = match.groups()
        dates.append((int(year), int(month), int(day or iso_day) if day or iso_day else None))
    return Counter(dates)


def _numeric_text(text: str) -> str:
    """Compare explicit quantities across common English and CJK written forms."""
    text = _named_dates(unicodedata.normalize("NFKC", text)).lower()
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
    return text


def numeric_values(text: str) -> set[str]:
    """Compare written quantities, including equivalent named/numeric calendar months."""
    values = re.findall(r"\d+(?:[.,]\d+)*%?", _numeric_text(text))
    return {str(int(value)) if value.isdigit() else value for value in values}


def validate_text(value: object, locale: str, original: str = "", protected: tuple[str, ...] = ()) -> str:
    if not isinstance(value, str):
        raise TypeError("Language output must be text")
    text: str = value
    if not 3 <= len(text.strip()) <= 3000:
        raise LocalizationValidationError("INVALID_TEXT", "Language output must be complete bounded text")
    if re.search(
        r"```|<think>|\[(?:add|insert|TODO)|［|example_parts|quote_span_id|confirmed_facts|repair_error",
        text,
        re.IGNORECASE,
    ):
        raise LocalizationValidationError(
            "UNFINISHED_TRANSLATION", "Language output contains placeholders or model instructions"
        )
    if locale == "zh-Hant":
        from opencc import OpenCC

        text = OpenCC("s2twp").convert(text)
    if locale == "ja" and not re.search(r"[\u3040-\u30ff]", text):
        raise LocalizationValidationError("WRONG_LANGUAGE", "Output must be Japanese")
    if locale == "zh-Hant" and not re.search(r"[\u3400-\u9fff]", text):
        raise LocalizationValidationError("WRONG_LANGUAGE", "Output must be Traditional Chinese")
    if locale != "en":
        remainder = text
        for name in protected:
            if name:
                remainder = remainder.replace(name, "")
        if re.search(r"[A-Za-z]+(?:\s+[A-Za-z]+){3,}", remainder):
            raise LocalizationValidationError(
                "UNTRANSLATED_PASSAGE", "Output contains an untranslated English passage"
            )
    if original and numeric_values(text) != numeric_values(original):
        raise LocalizationValidationError("NUMBER_CHANGED", "Translation changed a number")
    if original and calendar_dates(text) != calendar_dates(original):
        raise LocalizationValidationError("DATE_CHANGED", "Translation changed a calendar date")
    return text.strip()


class Localizer:
    def __init__(self, root: Path, model, invoke):
        self.root, self.model, self.invoke = root / "translation-cache", model, invoke

    async def questions(self, snapshot: dict, questions: list) -> list:
        result = []
        identity = None
        for ordinal, q in enumerate(questions, 1):
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
                    "ordinal": ordinal,
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
                cached_text = None
                if path.exists():
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                        if cached["version"] == VERSION:
                            cached_text = validate_text(cached["text"], q.locale, q.text, protected)
                    except (ValueError, TypeError, KeyError):
                        # A damaged cache must not make every explicit retry fail forever.
                        cached_text = None
                if cached_text is not None:
                    text = cached_text
                else:
                    text = await self.invoke(self.model.localize, payload)
                    try:
                        text = validate_text(text, q.locale, q.text, protected)
                    except LocalizationValidationError as exc:
                        exc.ordinal = ordinal
                        raise
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
