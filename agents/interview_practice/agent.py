"""ADK Web chat adapter for the same durable interview engine as the local browser."""

from __future__ import annotations

import asyncio
import shlex
import uuid
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from pathlib import Path

from google import genai
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions

from interview_simulator.coaching import example_count
from interview_simulator.config import Settings
from interview_simulator.engine import InterviewEngine
from interview_simulator.errors import safe_failure

_engine: InterviewEngine | None = None
_reports: dict[str, asyncio.Task[Path]] = {}
_binding: ContextVar[str | None] = ContextVar("interview_binding", default=None)


def engine() -> InterviewEngine:
    global _engine
    if _engine is None:
        _engine = InterviewEngine(Settings.load())
        from interview_simulator.adk_server import BOOTSTRAP

        if BOOTSTRAP is not None:
            _engine.providers = BOOTSTRAP
    return _engine


def _display(state: dict) -> str:
    if state["status"] == "preparation_failed":
        error = state.get("preparation_error") or {}
        if error.get("recovery") == "switch_provider" or error.get("code") in {
            "TEMPORARY_UNAVAILABLE",
            "RATE_LIMITED",
            "TIMEOUT",
            "PROVIDER_UNAVAILABLE",
        }:
            return "The selected AI model is unavailable. Switch to a local AI model or another provider. Your saved work is kept. Type `cancel` before changing settings, or `baseline` to use native fixed questions."
        return f"Preparation needs attention ({error.get('code', 'FAILED')}). Type `retry-preparation` or `baseline`, or `cancel`."
    if state["question"]:
        q = state["question"]
        return f"{q['ordinal']}/10 — {q['text']}\n\nType your answer, or type `skip`."
    if state["status"] == "paused":
        return "Practice paused. Type `resume` to continue, `review` to read saved answers, or `cancel`."
    if state["status"] == "cancelled":
        return "Practice cancelled. Type `jobs` and start a new run."
    return f"{state['closing']}\n\nType `report` to generate feedback, then `status` to check progress."


async def reply(message: str, session_run_id: str | None = None) -> str:
    practice = engine()
    _binding.set(session_run_id)
    command = message.strip()
    if not command or command.lower() in {"help", "jobs"}:
        jobs = practice.wiki.list_opportunities()
        ready = [j for j in jobs if j.ready]
        lines = ["Ready opportunities:"] + [f"- {j.reference} — {j.company}, {j.role}" for j in ready]
        if not ready:
            lines.append(
                "No prepared opportunities yet. Finish the manual PersonalWiki and InterviewWiki workflows first."
            )
        lines.append(
            "Start: `start company/opportunity en` (or `ja`, `zh-Hant`; add `adaptive` for bank-based order). Then answer each question in chat. Commands: `resume`, `skip`, `review`, `edit 1 revised answer`, `pause`, `cancel`, `report`, `stop-report`, `status`, `jobs`, `retry-preparation`, `baseline`, `allowance`, `revise-report`. For cloud text, append `cloud-ok` to start after reviewing your configured providers."
        )
        lines += ["Saved interviews (choose explicitly with `resume RUN_ID` or `history RUN_ID`):"]
        lines += [f"- {r['run_id']} — {r['opportunity']} ({r['status']})" for r in practice.store.list_runs()]
        return "\n".join(lines)
    if command.lower().startswith("start "):
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Invalid start command: {exc}"
        consent = "cloud-ok" in parts
        parts = [p for p in parts if p != "cloud-ok"]
        if len(parts) not in {2, 3, 4}:
            return "Use `start company/opportunity en` (or `ja`, `zh-Hant`; add `adaptive` for bank-based order)."
        locale = parts[2] if len(parts) >= 3 else "en"
        flow_mode = parts[3] if len(parts) == 4 else "fixed"
        from interview_simulator.adk_server import CLOUD_ALLOWED, cloud_providers

        if (
            hasattr(practice, "providers")
            and cloud_providers(practice.providers)
            and not (consent or CLOUD_ALLOWED)
        ):
            return "Configured text providers receive selected job/profile facts and confirmed answers. Audio stays local. Append `cloud-ok` to the start command to agree."
        state = await practice.start(
            parts[1], locale, flow_mode=flow_mode, cloud_consent=consent or CLOUD_ALLOWED
        )
        _binding.set(state["run_id"])
        return f"{state['greeting'] or ''}\n\n{state.get('flow_note') or ''}\n\n{_display(state)}"
    run_id = session_run_id
    if command.lower().startswith(("resume ", "history ")):
        parts = command.split()
        if len(parts) != 2:
            return "Use `resume RUN_ID` or `history RUN_ID`."
        saved = practice.store.get_run(parts[1])
        run_id = saved["run_id"]
        if command.lower().startswith("resume ") and saved["status"] not in {
            "active",
            "paused",
            "preparation_failed",
        }:
            return "This interview cannot be resumed. Use `history RUN_ID` to review it."
        _binding.set(run_id)
        command = "resume" if command.lower().startswith("resume ") else "review"
    if command.lower() == "resume":
        if run_id is None:
            return "No active interview. Type `jobs` to choose a prepared opportunity."
        saved = practice.store.get_run(run_id)
        if saved["status"] == "paused":
            return _display(await practice.action(run_id, "resume", saved["revision"]))
        return _display(await practice.state(run_id))
    if run_id is None:
        return "No active interview. Type `jobs` to see prepared opportunities."
    if command.lower() in {"retry-preparation", "baseline"}:
        return _display(await practice.retry_preparation(run_id, baseline=command.lower() == "baseline"))
    if command.lower() == "allowance":
        saved = practice.store.get_run(run_id)
        practice.store.grant_recovery(run_id, uuid.uuid4().hex, saved["revision"])
        return "Twelve additional attempts allowed. Type `report` to resume. Cloud calls may be billed."
    if command.lower() in {"revise-report", "revise-report cloud-ok"}:
        saved = practice.store.get_run(run_id)
        await practice.revise_report(
            run_id,
            practice.providers.plan,
            saved["revision"],
            uuid.uuid4().hex,
            command.lower().endswith(" cloud-ok"),
        )
        _reports.pop(run_id, None)
        return "New assessment revision created using your current saved model settings. Answers and earlier report files are kept. Type `report` to assess."
    if command.lower() in {"pause", "cancel"}:
        saved = practice.store.get_run(run_id)
        return _display(await practice.action(run_id, command.lower(), saved["revision"]))
    if command.lower() == "review":
        saved = practice.review(run_id)
        label = (
            "Answers locked after scoring began."
            if saved["report_state"] != "idle"
            else "Edit before scoring: `edit 1 revised answer`. Later questions keep their order."
        )
        return (
            label
            + "\n\n"
            + "\n\n".join(
                f"{a['ordinal']}. {saved['questions'][a['ordinal'] - 1]['text']}\n{a['text'] or '[skipped]'}"
                for a in saved["answers"]
            )
        )
    if command.lower().startswith("edit "):
        parts = command.split(maxsplit=2)
        if len(parts) != 3 or not parts[1].isdigit():
            return "Use `edit 1 revised answer` before scoring."
        saved = practice.store.get_run(run_id)
        await practice.edit(run_id, int(parts[1]), parts[2], uuid.uuid4().hex, saved["revision"])
        return "Answer revised. The existing question sequence is preserved. Type `resume` to continue."
    if command.lower() == "stop-report":
        task = _reports.get(run_id)
        if not task or task.done():
            return "No report is running; saved answers and scores are unchanged."
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return "Report stopped. Completed scores remain saved; answers remain locked. Type `report` to retry."
    if command.lower() in {"restart", "restart cloud-ok"}:
        from interview_simulator.adk_server import CLOUD_ALLOWED, cloud_providers

        consent = command.lower().endswith(" cloud-ok") or CLOUD_ALLOWED
        if hasattr(practice, "providers") and cloud_providers(practice.providers) and not consent:
            return (
                "Use `restart cloud-ok` to agree to the configured cloud text processing; audio stays local."
            )
        saved = practice.store.get_run(run_id)
        if saved["report_state"] == "idle" and saved["status"] in {"active", "paused", "answered"}:
            await practice.action(run_id, "cancel", saved["revision"])
        state = await practice.start(
            saved["opportunity"], saved["locale"], flow_mode=saved["flow_mode"], cloud_consent=consent
        )
        _binding.set(state["run_id"])
        return _display(state)
    if command.lower() == "status":
        task = _reports.get(run_id)
        saved = practice.store.get_run(run_id)
        if (saved.get("report_error") or {}).get("recovery") == "switch_provider":
            return "The selected AI model is unavailable. Switch to a local AI model or another provider. Your answers and completed scores are saved. Stop report work before changing settings, then use `revise-report` for a new assessment with the saved models."
        if task is None:
            report = practice.latest_report(run_id)
            return (
                f"{'Final report' if saved['report_state'] == 'complete' else 'Draft report'}: {report}; {example_count(saved)}/10 examples ready"
                if report
                else f"{len(saved['answers'])}/10 answered; report has not started."
            )
        if not task.done():
            scored = sum("score" in item for item in saved["evaluations"].values())
            return f"Report in progress: {len(saved['evaluations'])}/10 processed, {scored}/10 scored, {example_count(saved)}/10 examples ready. Type `status` again shortly."
        if task.cancelled():
            return "Report was interrupted. Type `report` to resume saved work."
        if error := task.exception():
            return f"Report stopped: {safe_failure(error)['message']}. Type `report` to retry saved work."
        return f"{'Final report' if saved['report_state'] == 'complete' else 'Draft report'} saved at {task.result()}; {example_count(saved)}/10 examples ready. Type `report` to resume missing work."
    if command.lower() == "report":
        saved = practice.store.get_run(run_id)
        if len(saved["answers"]) != 10:
            return "Answer or skip all ten questions before requesting the report."
        task = _reports.get(run_id)
        if task is None or task.done():
            practice.store.lock_scoring(run_id)
            _reports[run_id] = asyncio.create_task(practice.evaluate(run_id), name="interview-report")
        return "Report generation started. Type `status` to check progress."
    state = await practice.state(run_id)
    question = state["question"]
    if question is None:
        return "The interview is complete. Type `report` or `status`."
    practice.store.acknowledge_presentation(run_id, question["ordinal"], question["event_id"])
    skip = command.lower() == "skip"
    if not skip and len(message) > 6000:
        return "Keep the answer within 6,000 characters."
    following = await practice.submit(
        run_id,
        question["ordinal"],
        "" if skip else message,
        submission_id=f"chat-{uuid.uuid4().hex}",
        skipped=skip,
        expected_revision=state["revision"],
    )
    return _display(following)


class InterviewChatAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        parts = ctx.user_content.parts if ctx.user_content else []
        message = "\n".join(part.text for part in parts or [] if part.text)
        old_run = ctx.session.state.get("interview_run_id")
        try:
            text = await reply(message, old_run)
        except (ValueError, KeyError, RuntimeError, FileNotFoundError) as exc:
            text = f"Could not continue: {exc}. Type `resume` or `jobs` to inspect the current state."
        new_run = _binding.get()
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"interview_run_id": new_run} if new_run != old_run else {}),
            content=genai.types.Content(role="model", parts=[genai.types.Part(text=text)]),
        )


root_agent = InterviewChatAgent(
    name="interview_practice", description="Local, evidence-grounded interview practice"
)
