from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .adk_runtime import InterviewFlow, LocalAdk
from .config import Settings
from .coordination import serialized
from .errors import safe_failure
from .evaluation import skipped_evaluation
from .files import private_directory, reject_links
from .providers import ModelPlan, ProviderError, ProviderService
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
        self.providers = ProviderService(settings)
        self.adk = LocalAdk(settings, self.providers)
        self.flow = InterviewFlow(settings)

    @serialized("_start_lock")
    async def start(
        self,
        reference: str,
        locale: str,
        mode: str = "exam",
        flow_mode: str = "fixed",
        cloud_consent: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if request_id and (existing := self.store.request_run(request_id)):
            saved = self.store.get_run(existing)
            if (saved["opportunity"], saved["locale"], saved["flow_mode"]) != (reference, locale, flow_mode):
                raise ValueError("This preparation request belongs to another interview")
            return await self.state(existing)
        active = self.store.active_run()
        if active:
            raise ValueError(f"Resume the active interview first: {active}")
        snapshot = self.wiki.snapshot(reference)
        plan = ModelPlan()
        if hasattr(self, "providers"):
            plan = self.providers.plan
            if plan.cloud_providers and not cloud_consent:
                raise ValueError("Confirm cloud text processing before starting this run. Audio stays local.")
            await self.providers.validate(plan)
            snapshot["model_plan"] = plan.model_dump()
            snapshot["cloud_text_consent"] = {
                "approved": cloud_consent,
                "providers": sorted(plan.cloud_providers),
            }
        questions = make_fixed_questions(snapshot, locale)
        if flow_mode == "adaptive":
            snapshot["selection_pool"] = self.store.eligible_bank_questions(
                reference, locale, snapshot["hashes"]
            )
        run_id = self.store.create_run(
            reference, locale, snapshot, questions, mode, flow_mode, status="preparing", request_id=request_id
        )
        folder = self.wiki.simulation_dir(reference, run_id)
        _atomic_text(
            folder / "input-snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        )
        try:
            if hasattr(self, "providers") and plan.generate_questions:
                designer = LocalAdk(self.settings, self.providers, plan)
                designer.store, designer.run_id = self.store, run_id
                questions, provenance = await self._model_call(designer.design_questions, snapshot, questions)
                snapshot["question_design"] = provenance
                self.store.replace_preparation(run_id, snapshot, questions)
            await self._localize_preparation(run_id, snapshot, questions, plan)
            questions = self.store.get_run(run_id)["questions"]
            _atomic_text(
                folder / "input-snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
            )
            self.store.preparation_state(run_id, "ready")
            await self.flow.ensure_started(run_id, questions)
            self.store.preparation_state(run_id, "active")
        except BaseException as exc:
            self.store.preparation_state(run_id, "preparation_failed", safe_failure(exc))
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
        return await self.state(run_id)

    async def _localize_preparation(self, run_id, snapshot, questions, plan):
        if hasattr(self, "providers"):
            from .localization import Localizer

            designer = LocalAdk(self.settings, self.providers, plan)
            designer.store, designer.run_id = self.store, run_id
            questions = await Localizer(self.settings.state_root, designer, self._model_call).questions(
                snapshot, questions
            )
        self.store.replace_preparation(run_id, snapshot, questions)

    @serialized("_start_lock")
    async def retry_preparation(self, run_id: str, baseline: bool = False) -> dict:
        from .questions import Question

        run = self.store.get_run(run_id)
        if run["status"] != "preparation_failed" or self.store.active_run():
            raise ValueError("Retry only a failed undelivered preparation when no interview is active")
        self.store.preparation_state(run_id, "preparing")
        snapshot = run["snapshot"]
        plan = ModelPlan.model_validate(snapshot.get("model_plan", {}))
        questions = (
            make_fixed_questions(snapshot, run["locale"])
            if baseline
            else [Question(**q) for q in run["questions"]]
        )
        try:
            if baseline:
                # Vetted native baseline without untranslated evidence snippets.
                from dataclasses import replace

                from .questions import PROMPTS

                questions = [
                    replace(
                        q,
                        localization_version="native-baseline-v1",
                        original_text=q.text,
                        text=PROMPTS[run["locale"]][i].format(
                            role="target"
                            if run["locale"] == "en"
                            else "この職務"
                            if run["locale"] == "ja"
                            else "這個",
                            company=snapshot["company"],
                            requirement="the principal responsibility"
                            if run["locale"] == "en"
                            else "職務の主な責任"
                            if run["locale"] == "ja"
                            else "職位的主要責任",
                        ),
                    )
                    for i, q in enumerate(questions)
                ]
                snapshot["flow_note"] = {
                    "en": "Using native fixed questions with reduced personalization.",
                    "ja": "標準の日本語質問を使用します。個別の経歴の引用は省略します。",
                    "zh-Hant": "使用標準繁體中文題目，省略個人經歷的引用。",
                }[run["locale"]]
                self.store.replace_preparation(run_id, snapshot, questions)
            else:
                if plan.generate_questions and not snapshot.get("question_design"):
                    designer = LocalAdk(self.settings, self.providers, plan)
                    designer.store, designer.run_id = self.store, run_id
                    questions, provenance = await self._model_call(
                        designer.design_questions, snapshot, questions
                    )
                    snapshot["question_design"] = provenance
                    self.store.replace_preparation(run_id, snapshot, questions)
                await self._localize_preparation(run_id, snapshot, questions, plan)
            _atomic_text(
                self.wiki.simulation_dir(run["opportunity"], run_id) / "input-snapshot.json",
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            )
            self.store.preparation_state(run_id, "ready")
            await self.flow.ensure_started(run_id, self.store.get_run(run_id)["questions"])
            self.store.preparation_state(run_id, "active")
        except BaseException as exc:
            self.store.preparation_state(run_id, "preparation_failed", safe_failure(exc))
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
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
            run["status"] == "active"
            and run.get("flow_mode") == "adaptive"
            and 2 <= next_turn <= 10
            and next_turn not in run["selection_decisions"]
        ):
            chosen, decision = choose(run, next_turn)
            self.store.commit_selection(run_id, next_turn, chosen, decision)
            run = self.store.get_run(run_id)
        pending = await self._reconcile(run) if run["status"] in {"active", "answered"} else None
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
            "revision": run["revision"],
            "report_state": run["report_state"],
            "editable": run["report_state"] == "idle" and run["status"] in {"active", "answered", "paused"},
            "model_plan": run["snapshot"].get("model_plan"),
            "preparation_error": run.get("preparation_error"),
            "report_error": run.get("report_error"),
            "answered": len(run["answers"]),
            "greeting": {
                "en": "Welcome. Let's begin your interview.",
                "ja": "ようこそ。面接を始めましょう。",
                "zh-Hant": "歡迎，讓我們開始面試。",
            }[run["locale"]]
            if not run["answers"] and run["status"] == "active"
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
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        submission = submission_id or uuid.uuid4().hex
        self.store.submit(
            run_id, ordinal, submission, text, input_mode, skipped, raw_transcript, expected_revision
        )
        return await self.state(run_id)

    def review(self, run_id: str) -> dict[str, Any]:
        """Read-only history; never acknowledges an ADK event or selects a question."""
        run = self.store.get_run(run_id)
        return {
            key: run[key] for key in ("run_id", "revision", "status", "report_state", "questions", "answers")
        }

    async def edit(
        self, run_id: str, ordinal: int, text: str, submission_id: str, revision: int, skipped: bool = False
    ) -> dict[str, Any]:
        self.store.edit(run_id, ordinal, text, submission_id, revision, skipped)
        # No forward progression or question reselection on an edit.
        return self.review(run_id)

    async def action(self, run_id: str, action: str, revision: int) -> dict[str, Any]:
        self.store.transition(run_id, action, revision)
        return await self.state(run_id)

    @serialized("_cpu_lock")
    async def run_native(self, function, *args):
        import threading

        from .processes import native_cancel

        cancelled = threading.Event()
        token = native_cancel.set(cancelled)
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            # The worker stops/reaps its child before releasing the CPU queue.
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            native_cancel.reset(token)

    async def _model_call(self, function, *args):
        owner = getattr(function, "__self__", None)
        task = {
            "evaluate": "evaluation",
            "coach": "coaching",
            "design_questions": "questions",
            "summarize": "summary",
        }.get(getattr(function, "__name__", ""), "evaluation")
        binding = (
            (
                (owner.plan.localization or owner.plan.questions)
                if getattr(function, "__name__", "") == "localize"
                else getattr(owner.plan, task)
            )
            if isinstance(owner, LocalAdk)
            else None
        )
        if binding and binding.is_cloud:
            async with asyncio.timeout(360):
                return await function(*args)
        return await self._local_model_call(function, *args)

    @serialized("_cpu_lock")
    async def _local_model_call(self, function, *args):
        async with asyncio.timeout(360):
            return await function(*args)

    @serialized("_evaluation_lock")
    async def evaluate(self, run_id: str) -> Path:
        previous_error = self.store.get_run(run_id).get("report_error") or {}
        if previous_error.get("retry_at", 0) > time.time():
            raise ProviderError(
                "Wait for the provider retry delay before resuming saved work.",
                code="RATE_LIMITED",
                retry_after=previous_error["retry_at"] - time.time(),
                dispatch="not_sent",
            )
        self.store.lock_scoring(run_id)
        try:
            return await self._evaluate_work(run_id)
        except BaseException as exc:
            self.store.report_failure(run_id, safe_failure(exc))
            self.store.report_state(run_id, "interrupted")
            raise

    async def _evaluate_work(self, run_id: str) -> Path:
        frozen = self.store.lock_scoring(run_id)
        self.store.report_state(run_id, "running")
        self.store.report_failure(run_id, None)
        run = self.store.get_run(run_id)
        run["answers"], run["questions"] = frozen["answers"], frozen["questions"]
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
        assessor = self.adk
        if isinstance(assessor, LocalAdk):
            assessor = LocalAdk(
                self.settings,
                self.providers,
                ModelPlan.model_validate(run.get("report_options") or run["snapshot"].get("model_plan", {})),
            )
            assessor.store, assessor.run_id = self.store, run_id
        for answer in run["answers"]:
            ordinal = int(answer["ordinal"])
            existing = run["evaluations"].get(ordinal)
            if existing and "score" in existing and (answer["skipped"] or "coaching" in existing):
                continue
            question = {**run["questions"][ordinal - 1], "ordinal": ordinal}
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
                        assessor.evaluate, question, answer["text"], cited, requirement
                    )
                    prior_models = {
                        _scoring_identity(item.get("provenance", {}))
                        for item in run["evaluations"].values()
                        if "score" in item and item.get("provenance")
                    }
                    current_model = _scoring_identity(result.get("provenance", {}))
                    if prior_models and current_model not in prior_models:
                        raise ValueError("Loaded model differs from earlier assessments in this run")
                except Exception as exc:  # noqa: BLE001 - isolate a failed model call from saved answers
                    failure = safe_failure(exc)
                    result = {"unavailable": failure["message"], "failure": failure}
                    if isinstance(exc, ProviderError):
                        if exc.code == "RATE_LIMITED" and exc.retry_after is None:
                            failure["retry_at"] = time.time() + 60
                        if exc.retry_after is not None:
                            failure["retry_at"] = time.time() + exc.retry_after
                        self.store.report_failure(run_id, failure)
                        self.store.save_evaluation(run_id, ordinal, result)
                        break
            if "score" in result and not answer["skipped"] and "coaching" not in result:
                self.store.save_evaluation(run_id, ordinal, result)
                selected = question["fact_ids"] or tuple(facts)[:3]
                cited = {fid: facts[fid] for fid in selected if fid in facts}
                try:
                    coaching = await self._model_call(
                        assessor.coach, question, answer["text"], cited, copy.deepcopy(result)
                    )
                    scored_model = result.get("provenance", {}).get("gguf_sha256")
                    coached_model = coaching.get("provenance", {}).get("gguf_sha256")
                    plan = run.get("report_options") or run["snapshot"].get("model_plan", {})
                    same_local = not plan or (
                        plan.get("evaluation", {}).get("provider") == "local"
                        and plan.get("coaching", {}).get("provider") == "local"
                    )
                    if same_local and scored_model and scored_model != coached_model:
                        raise ValueError("Loaded model differs from the saved assessment")
                    result["coaching"] = coaching
                    result.pop("coaching_error", None)
                except Exception as exc:  # noqa: BLE001 - coaching failure must not revise the score
                    failure = safe_failure(exc)
                    result["coaching_error"] = failure["message"]
                    if isinstance(exc, ProviderError):
                        if exc.code == "RATE_LIMITED" and exc.retry_after is None:
                            failure["retry_at"] = time.time() + 60
                        if exc.retry_after is not None:
                            failure["retry_at"] = time.time() + exc.retry_after
                        self.store.report_failure(run_id, failure)
                        self.store.save_evaluation(run_id, ordinal, result)
                        break
            self.store.save_evaluation(run_id, ordinal, result)
        run = self.store.get_run(run_id)
        scored_all = len(run["evaluations"]) == 10 and all(
            "score" in item for item in run["evaluations"].values()
        )
        coached_all = scored_all and all(
            answer["skipped"] or "coaching" in run["evaluations"][answer["ordinal"]]
            for answer in run["answers"]
        )
        summary_complete = True
        if isinstance(assessor, LocalAdk) and assessor.plan.generate_summary:
            summary_complete = bool(run.get("summary_result"))
            if not summary_complete and coached_all:
                try:
                    summary = await self._model_call(assessor.summarize, run)
                    self.store.save_summary(run_id, summary)
                    summary_complete = True
                except Exception as exc:  # noqa: BLE001 - summary failure cannot alter saved scores.
                    failure = safe_failure(exc)
                    if isinstance(exc, ProviderError) and exc.retry_after is not None:
                        failure["retry_at"] = time.time() + exc.retry_after
                    self.store.report_failure(run_id, failure)
                    summary_complete = False
        run = self.store.get_run(run_id)
        final_state = (
            "complete"
            if coached_all and summary_complete
            else "retry_wait"
            if (run.get("report_error") or {}).get("code") == "RATE_LIMITED"
            else "incomplete"
        )
        run["report_state"] = final_state
        export_hash = hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest()
        self.store.checkpoint(run_id, "export", 0, export_hash, "running")
        folder = self.wiki.simulation_dir(run["opportunity"], run_id)
        text = render_report(run)
        try:
            report_path = self.latest_report(run_id) or folder / "report.md"
        except (ValueError, json.JSONDecodeError):
            # A retry can repair a broken manifest, but never overwrite old exports.
            report_path = folder / "report.md"
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
        manifest = {
            "schema_version": 1,
            "assessment_version": run["assessment_version"],
            "run_id": run_id,
            "opportunity": run["opportunity"],
            "locale": run["locale"],
            "model_configuration_at_export": run["snapshot"].get("model_plan", self.settings.model_name),
            "model_provenance": "Configured alias only; not an attestation of the loaded model or earlier assessments",
            "status": "complete"
            if coached_all and summary_complete
            else "summary-incomplete"
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
        self.store.checkpoint(run_id, "export", 0, export_hash, "succeeded")
        self.store.report_state(run_id, final_state)
        return report_path

    async def revise_report(
        self, run_id: str, plan: ModelPlan, revision: int, request_id: str, cloud_consent: bool
    ) -> dict:
        if plan.cloud_providers and not cloud_consent:
            raise ValueError("Confirm cloud text processing for the new report configuration")
        await self.providers.validate(plan)
        self.store.new_assessment_revision(run_id, plan.model_dump(), revision, request_id)
        return await self.state(run_id)

    def latest_report(self, run_id: str) -> Path | None:
        run = self.store.get_run(run_id)
        folder = self.wiki.simulation_dir(run["opportunity"], run_id)
        # Reject linked report paths even when they are uncommitted export remnants.
        for path in [folder / "report.md", *folder.glob("report-r*.md")]:
            reject_links(path)
        pointer = folder / "simulation-manifest.json"
        reject_links(pointer)
        if pointer.is_file():
            manifest = json.loads(pointer.read_text(encoding="utf-8"))
            if manifest.get("run_id") != run_id or manifest.get("opportunity") != run["opportunity"]:
                raise ValueError("Report manifest does not match this interview")
            names = manifest.get("files")
            if not isinstance(names, dict):
                raise ValueError("Report manifest is incomplete")
            reports = [
                name
                for name in names
                if name == "report.md"
                or (name.startswith("report-r") and name[8:-3].isdigit() and name.endswith(".md"))
            ]
            if len(reports) != 1:
                raise ValueError("Report manifest must name one committed report")
            for name, digest in names.items():
                if not isinstance(name, str) or Path(name).name != name:
                    raise ValueError("Report manifest contains an invalid file name")
                file = folder / name
                reject_links(file)
                if not file.is_file() or "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                    raise ValueError("Saved report export is incomplete or damaged; retry report export")
            if manifest.get("assessment_version", 0) != run["assessment_version"]:
                return None
            return folder / reports[0]
        with self.store.connect() as db:
            if db.execute(
                "SELECT 1 FROM tasks WHERE run_id=? AND kind='export' LIMIT 1", (run_id,)
            ).fetchone():
                return None  # No committed export pointer; do not expose a partial new report.
        # Compatibility for historical reports created before atomic manifests.
        paths = [(1, folder / "report.md")]
        paths.extend((int(p.stem[8:]), p) for p in folder.glob("report-r*.md") if p.stem[8:].isdigit())
        for _, path in sorted(paths, reverse=True):
            if path.is_file():
                return path
        return None


def _scoring_identity(provenance: dict) -> tuple:
    return (
        provenance.get("provider", "local"),
        provenance.get("gguf_sha256"),
        provenance.get("configuration_sha256"),
        provenance.get("returned_model"),
        provenance.get("model_digest"),
    )
