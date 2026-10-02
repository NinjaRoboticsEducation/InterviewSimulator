"""Safe presentation of saved reports. Charts use validated numbers, never model markup."""

from __future__ import annotations

import html
import math
from typing import Any

import nh3
from markdown_it import MarkdownIt

from .evaluation import DIMENSIONS
from .questions import CATEGORIES
from .report import DETAILS, NOTES

PARSER = MarkdownIt("js-default").enable("table")
CLEANER = nh3.Cleaner(
    tags={
        "p",
        "br",
        "hr",
        "strong",
        "em",
        "code",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "a",
    },
    attributes={"a": {"href", "title"}},
    url_schemes={"http", "https"},
    url_relative="deny",
    clean_content_tags={"script", "style", "iframe", "object"},
)


def safe_markdown(markdown: str) -> str:
    return CLEANER.clean(PARSER.render(markdown))


def statistics(run: dict[str, Any]) -> dict:
    evaluations = {int(k): v for k, v in run["evaluations"].items()}
    valid = {}
    for ordinal, evaluation in evaluations.items():
        score = evaluation.get("score")
        if type(score) in {float, int} and math.isfinite(score) and 0 <= score <= 100:
            valid[ordinal] = evaluation
    topics = []
    for category in CATEGORIES:
        ordinals = [i for i, q in enumerate(run["questions"], 1) if q["category"] == category]
        scores = [valid[i]["score"] for i in ordinals if i in valid]
        topics.append(
            {
                "category": category,
                "assessed": len(scores),
                "total": len(ordinals),
                "score": round(sum(scores) / len(scores), 1) if scores else None,
            }
        )
    dimensions = []
    for dimension in DIMENSIONS:
        values = [e.get("scores", {}).get(dimension) for e in valid.values()]
        values = [v for v in values if type(v) is int and 0 <= v <= 4]
        dimensions.append(
            {
                "dimension": dimension,
                "assessed": len(values),
                "score": round(sum(values) / len(values) * 25, 1) if values else None,
            }
        )
    return {
        "overall": round(sum(e["score"] for e in valid.values()) / len(valid), 1) if valid else None,
        "assessed": len(valid),
        "complete": len(valid) == 10,
        "topics": topics,
        "dimensions": dimensions,
        "skipped": sum(bool(a["skipped"]) for a in run["answers"]),
    }


def report_html(markdown: str, run: dict[str, Any] | None = None) -> str:
    body = safe_markdown(markdown)
    if run is None:
        return f'<article class="report-document">{body}</article>'
    locale = run["locale"]
    detail = DETAILS[locale]
    labels = {
        "en": (
            "Practice evidence",
            "Topic scores",
            "Rubric dimensions",
            "Provisional",
            "assessed",
            "Strengths to keep",
            "Next practice priorities",
            "Unavailable",
        ),
        "ja": (
            "練習で示した根拠",
            "分野別スコア",
            "評価項目",
            "暫定",
            "評価済み",
            "伸ばせる強み",
            "次の練習課題",
            "未評価",
        ),
        "zh-Hant": (
            "練習表現證據",
            "主題分數",
            "評分面向",
            "暫定",
            "已評估",
            "值得保留的優點",
            "下次練習重點",
            "尚無評估",
        ),
    }[locale]
    stats = statistics(run)
    escape = html.escape
    value = f"{stats['overall']:.1f}" if stats["overall"] is not None else "—"
    summary = (
        f'<section class="score-overview" aria-label="{escape(labels[0])}">'
        f'<div><span class="score-number">{value}</span><span> / 100</span></div>'
        f"<p>{stats['assessed']}/10 {escape(labels[4])}"
        f"{' · ' + escape(labels[3]) if not stats['complete'] else ''}</p>"
        f"<p>{escape(NOTES[locale][0])}</p></section>"
    )
    for heading, items, field in [
        (labels[1], stats["topics"], "category"),
        (labels[2], stats["dimensions"], "dimension"),
    ]:
        summary += f'<section class="score-section"><h2>{escape(heading)}</h2><table><tbody>'
        names = detail["categories"] if field == "category" else detail["dimension_names"]
        for item in items:
            name = escape(names.get(item[field], item[field]))
            score = item["score"]
            number = f"{score:.1f}/100" if score is not None else labels[7]
            bar = (
                f'<progress max="100" value="{score}" aria-label="{name}: {number}"></progress>'
                if score is not None
                else "—"
            )
            coverage = f"{item['assessed']}/{item.get('total', stats['assessed'])}"
            summary += f'<tr><th scope="row">{name}</th><td>{bar}</td><td>{escape(number)}</td><td>{coverage}</td></tr>'
        summary += "</tbody></table></section>"
    scored = [
        (int(i), e)
        for i, e in run["evaluations"].items()
        if type(e.get("score")) in {int, float}
        and math.isfinite(e["score"])
        and 0 <= e["score"] <= 100
        and not e.get("skipped")
    ]
    for heading, reverse, field in [(labels[5], True, "strength"), (labels[6], False, "improvement")]:
        summary += f'<section class="findings"><h2>{escape(heading)}</h2><ul>'
        for ordinal, evaluation in sorted(scored, key=lambda pair: pair[1]["score"], reverse=reverse)[:3]:
            summary += f"<li><strong>{ordinal}.</strong> {escape(str(evaluation.get(field, '')))}</li>"
        summary += "</ul></section>"
    return f'<div class="report-overview">{summary}</div><article class="report-document">{body}</article>'


def standalone_html(markdown: str, run: dict[str, Any], css: str) -> str:
    return (
        f'<!doctype html><html lang="{run["locale"]}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Interview practice report</title>"
        f'<style>{css}</style><main class="export-report">{report_html(markdown, run)}</main></html>'
    )
