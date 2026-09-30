"""ADK Web chat adapter for the same durable interview engine as the local browser."""

from __future__ import annotations

import asyncio
import shlex
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from google import genai
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions

from interview_simulator.config import Settings
from interview_simulator.engine import InterviewEngine

_engine: InterviewEngine | None = None
_reports: dict[str, asyncio.Task[Path]] = {}


def engine() -> InterviewEngine:
    global _engine
    if _engine is None:
        _engine = InterviewEngine(Settings.load())
    return _engine


def _display(state: dict) -> str:
    if state["question"]:
        q = state["question"]
        return f"{q['ordinal']}/10 — {q['text']}\n\nType your answer, or type `skip`."
    return f"{state['closing']}\n\nType `report` to generate feedback, then `status` to check progress."


async def reply(message: str, session_run_id: str | None = None) -> str:
    practice = engine()
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
            "Start: `start company/opportunity en` (or `ja`, `zh-Hant`; add `adaptive` for bank-based order). Then answer each question in chat. Commands: `resume`, `skip`, `report`, `status`, `jobs`."
        )
        return "\n".join(lines)
    if command.lower().startswith("start "):
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Invalid start command: {exc}"
        if len(parts) not in {2, 3, 4}:
            return "Use `start company/opportunity en` (or `ja`, `zh-Hant`; add `adaptive` for bank-based order)."
        locale = parts[2] if len(parts) >= 3 else "en"
        flow_mode = parts[3] if len(parts) == 4 else "fixed"
        state = await practice.start(parts[1], locale, flow_mode=flow_mode)
        return f"{state['greeting']}\n\n{state.get('flow_note') or ''}\n\n{_display(state)}"
    run_id = session_run_id or practice.store.active_run()
    if command.lower() == "resume":
        if run_id is None:
            return "No active interview. Type `jobs` to choose a prepared opportunity."
        return _display(await practice.state(run_id))
    if run_id is None:
        return "No active interview. Type `jobs` to see prepared opportunities."
    if command.lower() == "status":
        task = _reports.get(run_id)
        saved = practice.store.get_run(run_id)
        if task is None:
            report = practice.latest_report(run_id)
            return (
                f"Report: {report}"
                if report
                else f"{len(saved['answers'])}/10 answered; report has not started."
            )
        if not task.done():
            scored = sum("score" in item for item in saved["evaluations"].values())
            return f"Report in progress: {len(saved['evaluations'])}/10 processed, {scored}/10 scored. Type `status` again shortly."
        if task.cancelled():
            return "Report was interrupted. Type `report` to resume saved work."
        if error := task.exception():
            return f"Report stopped: {error}. Type `report` to retry saved work."
        return f"Report saved at {task.result()}. Open that Markdown file to review every answer."
    if command.lower() == "report":
        saved = practice.store.get_run(run_id)
        if len(saved["answers"]) != 10:
            return "Answer or skip all ten questions before requesting the report."
        task = _reports.get(run_id)
        if task is None or task.done():
            _reports[run_id] = asyncio.create_task(practice.evaluate(run_id))
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
        new_run = engine().store.active_run() or old_run
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"interview_run_id": new_run} if new_run != old_run else {}),
            content=genai.types.Content(role="model", parts=[genai.types.Part(text=text)]),
        )


root_agent = InterviewChatAgent(
    name="interview_practice", description="Local, evidence-grounded interview practice"
)
