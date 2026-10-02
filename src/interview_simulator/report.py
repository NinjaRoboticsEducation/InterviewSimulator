from __future__ import annotations

import re
from typing import Any

from .coaching import example_count, has_example

LABELS = {
    "en": (
        "Interview evaluation",
        "Interview qualification evidence score",
        "What worked",
        "Improve next",
        "Example answer",
        "Why it works",
        "Practice next",
    ),
    "ja": (
        "面接評価",
        "面接で示された適性スコア",
        "良かった点",
        "改善点",
        "回答例",
        "回答例の理由",
        "次の練習",
    ),
    "zh-Hant": (
        "面試評估",
        "面試表現佐證分數",
        "表現良好之處",
        "改進方向",
        "回答範例",
        "範例說明",
        "下一步練習",
    ),
}
NOTES = {
    "en": (
        "This score measures evidence demonstrated in this practice session; it is not a hiring prediction.",
        "Overall preparation",
        "Your strongest demonstrated area was",
        "The next area to practice is",
        "Assessment unavailable; retry this report without repeating the interview.",
        "No answer was submitted.",
        "Coaching example unavailable; retry report generation without repeating the interview.",
    ),
    "ja": (
        "このスコアは練習中に示された根拠を評価するもので、採用結果の予測ではありません。",
        "全体的な準備状況",
        "最もよく示せた分野：",
        "次に練習する分野：",
        "評価を完了できませんでした。面接を繰り返さずにレポートを再試行できます。",
        "回答は提出されていません。",
        "回答例を作成できませんでした。面接をやり直さずにレポートを再試行できます。",
    ),
    "zh-Hant": (
        "此分數衡量這次練習中呈現的佐證，並非錄取預測。",
        "整體準備情況",
        "表現最充分的領域：",
        "下一個建議練習的領域：",
        "評估暫時無法完成；可重新產生報告，無須重做面試。",
        "尚未提交答案。",
        "暫時無法產生回答範例；可重新產生報告，無須重做面試。",
    ),
}
DETAILS: dict[str, dict[str, Any]] = {
    "en": {
        "run": "Run",
        "opportunity": "Opportunity",
        "language": "Language",
        "not_available": "not available",
        "provisional": "provisional: {count}/10 assessed",
        "category": "Category",
        "confirmed": "Confirmed answer",
        "skipped": "[intentionally skipped]",
        "raw": "Recorded segment before corrections",
        "score": "Score",
        "reason": "Reason",
        "evidence": "Answer evidence",
        "dimensions": "Dimension ratings (0–4)",
        "dimension_names": {
            "relevance": "relevance",
            "specificity": "specificity",
            "reasoning": "reasoning",
            "clarity": "clarity",
            "reflection": "reflection",
        },
        "fact_ids": "Fact IDs",
        "source_ids": "Company source IDs",
        "none": "none",
        "outline": "Outline",
        "categories": {
            "personal": "Personal experience",
            "professionalism": "Professionalism",
            "portfolio": "Portfolio cases",
            "role": "Position-related",
            "company": "Company-related",
        },
    },
    "ja": {
        "run": "練習ID",
        "opportunity": "応募先",
        "language": "言語",
        "not_available": "評価なし",
        "provisional": "暫定評価：{count}/10問を評価済み",
        "category": "分野",
        "confirmed": "確定した回答",
        "skipped": "［意図的に回答を省略］",
        "raw": "録音区間の修正前の認識文",
        "score": "スコア",
        "reason": "評価理由",
        "evidence": "回答中の根拠",
        "dimensions": "項目別評価（0～4）",
        "dimension_names": {
            "relevance": "関連性",
            "specificity": "具体性",
            "reasoning": "論理性",
            "clarity": "明瞭さ",
            "reflection": "振り返り",
        },
        "fact_ids": "参照した事実ID",
        "source_ids": "参照した企業資料ID",
        "none": "なし",
        "outline": "回答の構成",
        "categories": {
            "personal": "個人の経験",
            "professionalism": "仕事への姿勢",
            "portfolio": "実績事例",
            "role": "職務に関する質問",
            "company": "企業に関する質問",
        },
    },
    "zh-Hant": {
        "run": "練習編號",
        "opportunity": "應徵機會",
        "language": "語言",
        "not_available": "尚無評分",
        "provisional": "暫定評估：已評分 {count}/10 題",
        "category": "類別",
        "confirmed": "確認後的回答",
        "skipped": "［刻意略過此題］",
        "raw": "錄音片段的原始辨識文字",
        "score": "分數",
        "reason": "評分原因",
        "evidence": "回答中的佐證",
        "dimensions": "各項評分（0–4）",
        "dimension_names": {
            "relevance": "相關性",
            "specificity": "具體程度",
            "reasoning": "推理分析",
            "clarity": "表達清晰度",
            "reflection": "反思能力",
        },
        "fact_ids": "參考事實編號",
        "source_ids": "參考公司資料編號",
        "none": "無",
        "outline": "回答架構",
        "categories": {
            "personal": "個人經驗",
            "professionalism": "專業態度",
            "portfolio": "作品與實績",
            "role": "職位相關",
            "company": "公司相關",
        },
    },
}


def _safe(value: Any) -> str:
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", text)


def render_report(run: dict[str, Any]) -> str:
    locale = run["locale"]
    title, score_label, good, improve, example, why, practice = LABELS[locale]
    score_note, overall, strongest, next_area, unavailable, missing, coaching_unavailable = NOTES[locale]
    detail = DETAILS[locale]
    examples = example_count(run)
    answers = {int(a["ordinal"]): a for a in run["answers"]}
    evaluations = {int(k): v for k, v in run["evaluations"].items()}
    scored = [evaluations[i]["score"] for i in range(1, 11) if i in evaluations and "score" in evaluations[i]]
    complete = len(answers) == 10 and len(scored) == 10
    score = f"{sum(scored) / len(scored):.1f}/100" if scored else detail["not_available"]
    qualifier = "" if complete else f" ({detail['provisional'].format(count=len(scored))})"
    flow_labels = {
        "en": (
            "Interview flow",
            "fixed",
            "adaptive",
            "Question choice",
            "fixed fallback",
            "bank question",
            "Model",
        ),
        "ja": ("質問の進行", "固定", "適応", "質問の選択", "固定質問", "質問バンク", "モデル"),
        "zh-Hant": ("題目流程", "固定", "適應", "題目選擇", "固定題", "題庫題", "模型"),
    }[locale]
    flow_name = flow_labels[2] if run.get("flow_mode") == "adaptive" else flow_labels[1]
    lines = [
        f"# {title}",
        "",
        f"- {detail['run']}: {_safe(run['run_id'])}",
        f"- {detail['opportunity']}: {_safe(run['opportunity'])}",
        f"- {detail['language']}: `{locale}`",
        f"- {flow_labels[0]}: {flow_name}",
        f"- {score_label}: **{score}{qualifier}**",
        "",
        score_note,
        "",
    ]
    if run.get("report_state") in {"incomplete", "interrupted", "running", "retry_wait"}:
        lines.extend(
            [
                {
                    "en": "Report work is incomplete. Resume missing assessment, coaching or summary work; saved scores remain unchanged.",
                    "ja": "レポート処理は未完了です。未完了の評価・助言・全体の練習課題を再開できます。保存済みスコアは変更されません。",
                    "zh-Hant": "報告處理尚未完成。可接續未完成的評估、指導或摘要；已儲存分數保持不變。",
                }[locale],
                "",
            ]
        )
    lines.extend(
        [
            {
                "en": "AI feedback is practice advice, not verified career evidence. Check every suggested result or detail against your real experience before using it.",
                "ja": "AIの助言は練習用であり、確認済みの経歴ではありません。提案された成果や詳細を実際の経験と照合してから使ってください。",
                "zh-Hant": "AI回饋是練習建議，不是已確認的職涯證據。使用任何建議的成果或細節前，請與真實經歷核對。",
            }[locale],
            "",
        ]
    )
    plan = run.get("report_options") or run["snapshot"].get("model_plan", {})
    if plan:
        headings = {
            "en": ("Text models for this run", "Task", "Provider", "Model"),
            "ja": ("この練習のテキストモデル", "処理", "提供元", "モデル"),
            "zh-Hant": ("本次練習的文字模型", "任務", "供應商", "模型"),
        }[locale]
        tasks = {
            "en": {
                "questions": "Question preparation",
                "evaluation": "Assessment",
                "coaching": "Coaching",
                "summary": "Priorities",
            },
            "ja": {
                "questions": "質問の準備",
                "evaluation": "評価",
                "coaching": "助言",
                "summary": "練習課題",
            },
            "zh-Hant": {
                "questions": "題目準備",
                "evaluation": "評估",
                "coaching": "指導",
                "summary": "練習重點",
            },
        }[locale]
        lines.extend(
            [
                f"### {headings[0]}",
                "",
                f"| {headings[1]} | {headings[2]} | {headings[3]} |",
                "| --- | --- | --- |",
            ]
        )
        for task, label in tasks.items():
            if task in {"questions", "summary"} and not plan.get("generate_" + task):
                continue
            binding = plan[task]
            lines.append(f"| {label} | {_safe(binding['provider'])} | {_safe(binding['model'])} |")
        lines.append("")
    category_scores: dict[str, list[float]] = {}
    for index, question in enumerate(run["questions"], 1):
        evaluation = evaluations.get(index, {})
        if "score" in evaluation:
            category_scores.setdefault(question["category"], []).append(evaluation["score"])
    if category_scores:
        averages = {name: sum(values) / len(values) for name, values in category_scores.items()}
        best = max(averages, key=lambda name: averages[name])
        weakest = min(averages, key=lambda name: averages[name])
        if len(set(averages.values())) == 1:
            tie = {
                "en": "Assessed topics have the same average. Use the per-answer feedback to choose your next practice priority.",
                "ja": "評価済み分野の平均は同じです。回答ごとの助言から次の練習課題を選んでください。",
                "zh-Hant": "已評估主題的平均分數相同。請根據逐題回饋選擇下一個練習重點。",
            }[locale]
            lines.extend([f"## {overall}", "", tie, ""])
        else:
            lines.extend(
                [
                    f"## {overall}",
                    "",
                    f"{strongest} **{detail['categories'].get(best, best)}** ({averages[best]:.1f}/100).",
                    f"{next_area} **{detail['categories'].get(weakest, weakest)}** ({averages[weakest]:.1f}/100).",
                    "",
                ]
            )
    if category_scores:
        heading = {"en": "Topic scores", "ja": "分野別スコア", "zh-Hant": "主題分數"}[locale]
        lines.extend([f"### {heading}", "", f"| {detail['category']} | {detail['score']} |", "| --- | --- |"])
        for category, values in category_scores.items():
            lines.append(
                f"| {detail['categories'][category]} | {sum(values) / len(values):.1f}/100 ({len(values)}/2) |"
            )
        lines.append("")
    for index, question in enumerate(run["questions"], 1):
        answer = answers.get(index)
        evaluation = evaluations.get(index)
        lines.extend(
            [
                f"## {index}. {_safe(question['text'])}",
                "",
                f"{detail['category']}: {_safe(detail['categories'].get(question['category'], question['category']))}",
                "",
            ]
        )
        decision = run.get("selection_decisions", {}).get(index)
        if decision:
            kind = flow_labels[4] if decision["fallback"] else flow_labels[5]
            lines.extend(
                [
                    (
                        f"{flow_labels[3]}: `{_safe(decision['policy_version'])}`; {kind}; "
                        f"{decision['candidate_count']}."
                    ),
                    "",
                ]
            )
        if question.get("source_ids"):
            lines.extend(
                [
                    f"{detail['source_ids']}: "
                    + ", ".join(f"`{_safe(source_id)}`" for source_id in question["source_ids"]),
                    "",
                ]
            )
        if answer is None:
            lines.extend([missing, ""])
            continue
        transcript = detail["skipped"] if answer["skipped"] else answer["text"]
        lines.extend(
            [f"**{detail['confirmed']}**", "", *["> " + _safe(line) for line in transcript.splitlines()], ""]
        )
        raw_transcript = answer.get("raw_transcript")
        if raw_transcript and raw_transcript != answer["text"]:
            lines.extend([f"**{detail['raw']}:** {_safe(raw_transcript)}", ""])
        if evaluation is None or "score" not in evaluation:
            lines.extend([unavailable, "", f"**{example}:** {coaching_unavailable}", ""])
            continue
        lines.extend(
            [
                f"**{detail['score']}:** {evaluation['score']:.1f}/100",
                "",
                f"**{good}:** {_safe(evaluation['strength'])}",
                "",
                f"**{improve}:** {_safe(evaluation['improvement'])}",
                "",
                f"**{detail['reason']}:** {_safe(evaluation['reason'])}",
                "",
            ]
        )
        if evaluation.get("quote"):
            lines.extend([f"**{detail['evidence']}:** “{_safe(evaluation['quote'])}”", ""])
        scores = evaluation.get("scores", {})
        if scores:
            lines.extend(
                [
                    f"**{detail['dimensions']}:** "
                    + ", ".join(
                        f"{detail['dimension_names'].get(key, key)} {value}" for key, value in scores.items()
                    ),
                    "",
                ]
            )
        provenance = evaluation.get("provenance")
        if provenance:
            identity = (
                f"{provenance['gguf_file']} ({provenance['gguf_sha256']})"
                if "gguf_file" in provenance
                else f"{provenance.get('provider', 'unknown')} / {provenance.get('returned_model', provenance.get('requested_model', 'unknown'))}"
            )
            lines.extend(
                [
                    (f"{flow_labels[6]}: {_safe(identity)}; `{_safe(provenance['rubric_version'])}`."),
                    "",
                ]
            )
        coaching = evaluation.get("coaching")
        if has_example(coaching):
            lines.extend(
                [
                    f"**{example}:** {_safe(coaching['example'])}",
                    "",
                    f"**{why}:** {_safe(coaching['why_it_works'])}",
                    "",
                    f"**{detail['fact_ids']}:** {', '.join('`' + _safe(f) + '`' for f in coaching['fact_ids']) or detail['none']}",
                    "",
                    f"**{detail['outline']}:** {_safe(coaching['outline'])}",
                    "",
                    f"**{practice}:** {_safe(coaching['next_action'])}",
                    "",
                ]
            )
            if coaching.get("source_ids"):
                lines.extend(
                    [
                        f"**{detail['source_ids']}:** "
                        + ", ".join("`" + _safe(item) + "`" for item in coaching["source_ids"]),
                        "",
                    ]
                )
            if coaching.get("provenance"):
                identity = coaching["provenance"]
                name = identity.get(
                    "gguf_file", identity.get("returned_model", identity.get("requested_model", "unknown"))
                )
                lines.extend(
                    [
                        f"{flow_labels[6]} ({why}): {_safe(identity.get('provider', 'local'))} / {_safe(name)}",
                        "",
                    ]
                )
        else:
            lines.extend([f"**{example}:** {coaching_unavailable}", ""])
    if run.get("summary"):
        lines.extend(["", f"## {overall}", "", _safe(run["summary"])])
    if examples < 10 or not complete or run.get("report_state") not in {None, "complete"}:
        notice = {
            "en": f"DRAFT — {len(scored)}/10 scored; {examples}/10 validated examples ready. Resume missing work before this report is final.",
            "ja": f"下書き — 採点{len(scored)}/10、検証済み回答例{examples}/10。最終版には未完了の処理を再開してください。",
            "zh-Hant": f"草稿 — 已評分{len(scored)}/10，已驗證回答範例{examples}/10。請繼續未完成項目後再產生最終報告。",
        }[locale]
        lines[2:2] = [notice, ""]
    return "\n".join(lines).rstrip() + "\n"
