from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .adk_runtime import InterviewFlow, LocalAdk
from .config import Settings
from .coordination import serialized
from .evaluation import skipped_evaluation
from .files import private_directory, reject_links
from .questions import make_fixed_questions
from .report import render_report
from .selection import choose
from .storage import Store
from .wiki import WikiAdapter


def _atomic_text(path: Path, text: str) -> None:
    private_directory(path.parent)
    reject_links(path)
    descriptor, temp = tempfile.mkstemp(prefix=".sim-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        Path(temp).replace(path)
    finally:
        Path(temp).unlink(missing_ok=True)


class InterviewEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.wiki = WikiAdapter(settings.wiki_root)
        self.store = Store(settings.state_root / "question-bank.sqlite")
        self.adk = LocalAdk(settings)
        self.flow = InterviewFlow(settings)

    @serialized("_start_lock")
    async def start(
        self, reference: str, locale: str, mode: str = "exam", flow_mode: str = "fixed"
    ) -> dict[str, Any]:
        active = self.store.active_run()
        if active:
            raise ValueError(f"Resume the active interview first: {active}")
        snapshot = self.wiki.snapshot(reference)
        questions = make_fixed_questions(snapshot, locale)
        if flow_mode == "adaptive":
            snapshot["selection_pool"] = self.store.eligible_bank_questions(
                reference, locale, snapshot["hashes"]
            )
        run_id = self.store.create_run(reference, locale, snapshot, questions, mode, flow_mode)
        folder = self.wiki.simulation_dir(reference, run_id)
        _atomic_text(
            folder / "input-snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        )
        await self.flow.start(run_id, [q.to_dict() for q in questions])
        return await self.state(run_id)

    def _verify_snapshot(self, run: dict[str, Any]) -> None:
        path = self.wiki.simulation_dir(run["opportunity"], run["run_id"]) / "input-snapshot.json"
        reject_links(path)
        if not path.exists():
            _atomic_text(path, json.dumps(run["snapshot"], ensure_ascii=False, indent=2) + "\n")
        elif json.loads(path.read_text(encoding="utf-8")) != run["snapshot"]:
            raise ValueError("Frozen input snapshot was changed; restore it from a trusted backup")

    async def _reconcile(self, run: dict[str, Any]) -> tuple[int, str] | None:
        """Deliver saved answers after a crash before ADK acknowledgement."""
        self._verify_snapshot(run)
        await self.flow.ensure_started(run["run_id"], run["questions"])
        answers = {int(item["ordinal"]): item for item in run["answers"]}
        for _ in range(11):
            pending = await self.flow.pending(run["run_id"])
            if pending is None:
                if len(answers) == 10:
                    return None
                raise RuntimeError("ADK ended before all ten interview turns")
            ordinal, interrupt_id = pending
            if ordinal in answers:
                answer = answers[ordinal]
                await self.flow.resume(
                    run["run_id"],
                    run["questions"],
                    interrupt_id,
                    answer["text"] if not answer["skipped"] else "[skipped]",
                )
                continue
            if ordinal != len(answers) + 1:
                raise RuntimeError("ADK turn and saved answers disagree")
            return pending
        raise RuntimeError("ADK reconciliation did not converge")

    @serialized("_state_lock")
    async def state(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        next_turn = len(run["answers"]) + 1
        if (
            run.get("flow_mode") == "adaptive"
            and 2 <= next_turn <= 10
            and next_turn not in run["selection_decisions"]
        ):
            chosen, decision = choose(run, next_turn)
            self.store.commit_selection(run_id, next_turn, chosen, decision)
            run = self.store.get_run(run_id)
        pending = await self._reconcile(run)
        next_ordinal = len(run["answers"]) + 1
        question = (
            self.store.present(run_id, next_ordinal)
            if pending and next_ordinal <= 10 and run["status"] == "active"
            else None
        )
        return {
            "run_id": run_id,
            "opportunity": run["opportunity"],
            "locale": run["locale"],
            "mode": run["mode"],
            "flow_mode": run.get("flow_mode", "fixed"),
            "flow_note": run["snapshot"].get("flow_note"),
            "status": run["status"],
            "answered": len(run["answers"]),
            "greeting": {
                "en": "Welcome. Let's begin your interview.",
                "ja": "ようこそ。面接を始めましょう。",
                "zh-Hant": "歡迎，讓我們開始面試。",
            }[run["locale"]]
            if not run["answers"]
            else None,
            "closing": {
                "en": "Thank you for your time. The interview is complete.",
                "ja": "本日はありがとうございました。面接は終了です。",
                "zh-Hant": "感謝你的時間，面試已結束。",
            }[run["locale"]]
            if run["status"] == "answered"
            else None,
            "question": question,
        }

    async def submit(
        self,
        run_id: str,
        ordinal: int,
        text: str,
        submission_id: str | None = None,
        input_mode: str = "text",
        skipped: bool = False,
        raw_transcript: str | None = None,
    ) -> dict[str, Any]:
        submission = submission_id or uuid.uuid4().hex
        self.store.submit(run_id, ordinal, submission, text, input_mode, skipped, raw_transcript)
        return await self.state(run_id)

    @serialized("_cpu_lock")
    async def run_native(self, function, *args):
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Do not release the CPU queue while a bounded native job still runs.
            await task
            raise

    @serialized("_cpu_lock")
    async def _model_call(self, function, *args):
        async with asyncio.timeout(360):
            return await function(*args)

    @serialized("_evaluation_lock")
    async def evaluate(self, run_id: str) -> Path:
        run = self.store.get_run(run_id)
        self._verify_snapshot(run)
        if len(run["answers"]) != 10:
            raise ValueError("Complete or explicitly skip all ten questions before final evaluation")
        facts = {
            item["fact_id"]: item["statement"]
            for item in run["snapshot"]["inputs"]["candidate"]["facts"]
            if item.get("confidence") == "confirmed" and item.get("sensitive") is False
        }
        requirements = {
            item["requirement_id"]: item["statement"]
            for item in run["snapshot"]["inputs"]["requirements"]["requirements"]
        }
        for answer in run["answers"]:
            ordinal = int(answer["ordinal"])
            existing = run["evaluations"].get(ordinal)
            if existing and "score" in existing and (answer["skipped"] or "coaching" in existing):
                continue
            question = run["questions"][ordinal - 1]
            if existing and "score" in existing:
                result = dict(existing)
            elif answer["skipped"]:
                result = skipped_evaluation(run["locale"])
            else:
                selected = question["fact_ids"] or tuple(facts)[:3]
                cited = {fid: facts[fid] for fid in selected if fid in facts}
                requirement = "; ".join(requirements[rid] for rid in question["requirement_ids"])
                try:
                    result = await self._model_call(
                        self.adk.evaluate, question, answer["text"], cited, requirement
                    )
                    prior_models = {
                        item.get("provenance", {}).get("gguf_sha256")
                        for item in run["evaluations"].values()
                        if "score" in item and item.get("provenance")
                    }
                    current_model = result.get("provenance", {}).get("gguf_sha256")
                    if prior_models and current_model not in prior_models:
                        raise ValueError("Loaded model differs from earlier assessments in this run")
                except Exception as exc:  # noqa: BLE001 - isolate a failed model call from saved answers
                    result = {"unavailable": str(exc)}
            if "score" in result and not answer["skipped"] and "coaching" not in result:
                self.store.save_evaluation(run_id, ordinal, result)
                selected = question["fact_ids"] or tuple(facts)[:3]
                cited = {fid: facts[fid] for fid in selected if fid in facts}
                try:
                    coaching = await self._model_call(
                        self.adk.coach, question, answer["text"], cited, copy.deepcopy(result)
                    )
                    scored_model = result.get("provenance", {}).get("gguf_sha256")
                    coached_model = coaching.get("provenance", {}).get("gguf_sha256")
                    if scored_model and scored_model != coached_model:
                        raise ValueError("Loaded model differs from the saved assessment")
                    result["coaching"] = coaching
                    result.pop("coaching_error", None)
                except Exception as exc:  # noqa: BLE001 - coaching failure must not revise the score
                    result["coaching_error"] = str(exc)
            self.store.save_evaluation(run_id, ordinal, result)
        run = self.store.get_run(run_id)
        folder = self.wiki.simulation_dir(run["opportunity"], run_id)
        text = render_report(run)
        report_path = self.latest_report(run_id) or folder / "report.md"
        reject_links(report_path)
        if report_path.is_file() and report_path.read_text(encoding="utf-8") != text:
            revisions = list(folder.glob("report-r*.md"))
            numbers = [
                int(p.stem.removeprefix("report-r"))
                for p in revisions
                if p.stem.removeprefix("report-r").isdigit()
            ]
            report_path = folder / f"report-r{max([1, *numbers]) + 1:02d}.md"
        _atomic_text(report_path, text)
        run_export = folder / f"run-export-{report_path.stem}.json"
        _atomic_text(run_export, json.dumps(run, ensure_ascii=False, indent=2) + "\n")
        files = [folder / "input-snapshot.json", run_export, report_path]
        scored_all = len(run["evaluations"]) == 10 and all(
            "score" in item for item in run["evaluations"].values()
        )
        coached_all = scored_all and all(
            answer["skipped"] or "coaching" in run["evaluations"][answer["ordinal"]]
            for answer in run["answers"]
        )
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "opportunity": run["opportunity"],
            "locale": run["locale"],
            "model_configuration_at_export": self.settings.model_name,
            "model_provenance": "Configured alias only; not an attestation of the loaded model or earlier assessments",
            "status": "complete"
            if coached_all
            else "coaching-incomplete"
            if scored_all
            else "assessment-incomplete",
            "files": {file.name: "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
        }
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        _atomic_text(folder / f"simulation-manifest-{report_path.stem}.json", manifest_text)
        # This pointer changes last. Older report/export pairs remain immutable.
        _atomic_text(folder / "simulation-manifest.json", manifest_text)
        _atomic_text(folder / "run.json", json.dumps(run, ensure_ascii=False, indent=2) + "\n")
        return report_path

    def latest_report(self, run_id: str) -> Path | None:
        run = self.store.get_run(run_id)
        folder = self.wiki.simulation_dir(run["opportunity"], run_id)
        paths = [(1, folder / "report.md")]
        paths.extend((int(p.stem[8:]), p) for p in folder.glob("report-r*.md") if p.stem[8:].isdigit())
        for _, path in sorted(paths, reverse=True):
            reject_links(path)
            if path.is_file():
                return path
        return None
