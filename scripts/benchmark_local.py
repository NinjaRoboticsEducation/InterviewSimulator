"""Synthetic offline language/latency check; never reads PersonalWiki."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from interview_simulator.adk_runtime import LocalAdk
from interview_simulator.config import Settings
from interview_simulator.provenance import model_identity

CASES = {
    "en": (
        "Tell me about a project you delivered and its outcome.",
        "I built a test service, wrote checks for its main behavior, and documented it for colleagues. I do not have a verified adoption number.",
        "Built a test service.",
    ),
    "ja": (
        "担当したプロジェクトと成果を説明してください。",
        "私はテスト用サービスを構築し、主要な動作の確認と文書化を行いました。利用者数は確認できていません。",
        "テスト用サービスを構築した。",
    ),
    "zh-Hant": (
        "請說明你完成的一個專案及其成果。",
        "我建立了一個測試服務，檢查主要功能並為同事撰寫文件。我沒有可查證的使用人數。",
        "建立了一個測試服務。",
    ),
}


async def main(model_file: Path, output: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    temporary = tempfile.TemporaryDirectory(prefix="interview-benchmark-")
    settings = Settings(
        root, root / "InterviewWiki", Path(temporary.name).resolve(), model_path=model_file.resolve()
    )
    adk = LocalAdk(settings)
    results: dict = {
        "model": model_file.name,
        "cases": [],
        "started_at": datetime.now(UTC).isoformat(),
        "benchmark_version": "durability-v3",
        "output_limits": {
            "assessment": adk.plan.evaluation.max_output_tokens,
            "coaching": adk.plan.coaching.max_output_tokens,
        },
    }
    started = time.monotonic()
    identity = await model_identity(settings)
    results["model_sha256"] = identity["gguf_sha256"]
    results["identity_seconds"] = round(time.monotonic() - started, 2)
    print("IDENTITY", model_file.name, results["identity_seconds"], flush=True)
    for locale, (question_text, answer, fact) in CASES.items():
        question = {
            "locale": locale,
            "text": question_text,
            "category": "portfolio",
            "fact_ids": ["fact-synthetic"],
            "requirement_ids": ["req-synthetic"],
        }
        row = {"locale": locale, "synthetic": True}
        began = time.monotonic()
        try:
            evaluation = await adk.evaluate(
                question, answer, {"fact-synthetic": fact}, "Deliver reliable Python services"
            )
            row["assessment_seconds"] = round(time.monotonic() - began, 2)
            row["score"] = evaluation["score"]
            row["quote_valid"] = evaluation["quote"] in answer
            row["assessment_language"] = {
                key: evaluation[key] for key in ("strength", "improvement", "reason")
            }
            row["assessment_prompt_sha256"] = evaluation["provenance"]["prompt_sha256"]
            row["assessment_model_sha256"] = evaluation["provenance"]["gguf_sha256"]
            if locale in CASES:
                began = time.monotonic()
                coaching = await adk.coach(question, answer, {"fact-synthetic": fact}, evaluation)
                row["coaching_seconds"] = round(time.monotonic() - began, 2)
                row["coaching_grounded"] = bool(coaching.get("grounding_review")) and not any(
                    bracket in coaching["example"] for bracket in ("[add", "［")
                )
                row["coaching_example"] = coaching["example"]
                row["coaching_advice"] = {
                    key: coaching[key] for key in ("why_it_works", "outline", "next_action")
                }
                row["coaching_prompt_sha256"] = coaching["provenance"]["prompt_sha256"]
                row["coaching_model_sha256"] = coaching["provenance"]["gguf_sha256"]
        except Exception as exc:  # noqa: BLE001 - record each benchmark failure and continue.
            row["error"] = f"{type(exc).__name__}: {exc}"
        results["cases"].append(row)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            "CASE",
            locale,
            row.get("assessment_seconds"),
            row.get("coaching_seconds"),
            row.get("error", "ok"),
            flush=True,
        )
    temporary.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.model, args.output))
