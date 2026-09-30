from __future__ import annotations

import asyncio
import subprocess
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from filelock import FileLock
from interviewwiki.errors import InterviewWikiError
from interviewwiki.util import parse_ref
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .doctor import diagnostics
from .engine import InterviewEngine
from .files import reject_links
from .security import REQUEST_TOKEN, LocalRequestMiddleware
from .speech import Speech


@asynccontextmanager
async def lifespan(app):
    lock_path = engine.settings.state_root / "server.lock"
    reject_links(lock_path)
    lease = FileLock(lock_path, timeout=0)
    with lease:
        try:
            yield
        finally:
            tasks = list(report_tasks.values())
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            report_tasks.clear()


app = FastAPI(title="Interview Simulator", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(LocalRequestMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
engine = InterviewEngine(Settings.load())
speech = Speech()
report_tasks: dict[str, asyncio.Task[Path]] = {}


class StartRequest(BaseModel):
    opportunity: str = Field(min_length=3, max_length=200)
    locale: Literal["en", "ja", "zh-Hant"] = "en"
    mode: Literal["exam"] = "exam"
    flow_mode: Literal["fixed", "adaptive"] = "fixed"


class AnswerRequest(BaseModel):
    ordinal: int = Field(ge=1, le=10)
    text: str = Field(default="", max_length=6000)
    submission_id: str = Field(min_length=1, max_length=128)
    input_mode: Literal["text", "voice"] = "text"
    skipped: bool = False
    raw_transcript: str | None = Field(default=None, max_length=6000)


def read_report(path: Path) -> str:
    reject_links(path)
    return path.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML.replace("__REQUEST_TOKEN__", REQUEST_TOKEN)


@app.get("/api/opportunities")
def opportunities():
    return [item.__dict__ for item in engine.wiki.list_opportunities()]


@app.get("/api/active")
def active():
    return {"run_id": engine.store.active_run()}


@app.get("/api/recent")
def recent():
    return {"run_id": engine.store.recent_run()}


@app.get("/api/history")
def history(opportunity: str, locale: str = "en"):
    try:
        parse_ref(opportunity)
        if locale not in {"en", "ja", "zh-Hant"}:
            raise ValueError("Unsupported language")
        return engine.store.practice_profile(opportunity, locale)
    except (ValueError, InterviewWikiError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/doctor")
def doctor():
    return diagnostics(engine.settings)


@app.post("/api/runs")
async def start(request: StartRequest):
    try:
        return await engine.start(request.opportunity, request.locale, request.mode, request.flow_mode)
    except (ValueError, FileNotFoundError, KeyError, InterviewWikiError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/runs/{run_id}")
async def state(run_id: str):
    try:
        return await engine.state(run_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/runs/{run_id}/answers")
async def answer(run_id: str, request: AnswerRequest):
    try:
        return await engine.submit(
            run_id,
            request.ordinal,
            request.text,
            request.submission_id,
            request.input_mode,
            request.skipped,
            request.raw_transcript,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/runs/{run_id}/present/{ordinal}/{event_id}")
def acknowledge(run_id: str, ordinal: int, event_id: str):
    try:
        engine.store.acknowledge_presentation(run_id, ordinal, event_id)
        return {"acknowledged": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/runs/{run_id}/report")
async def report(run_id: str):
    try:
        path = await engine.evaluate(run_id)
        return {"path": str(path), "report": read_report(path)}
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/runs/{run_id}/report/start")
async def start_report(run_id: str):
    try:
        run = engine.store.get_run(run_id)
        if len(run["answers"]) != 10:
            raise ValueError("Complete or skip all ten questions first")
        task = report_tasks.get(run_id)
        if task is None or task.done():
            report_tasks[run_id] = asyncio.create_task(engine.evaluate(run_id))
        return {"started": True}
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/runs/{run_id}/report/status")
def report_status(run_id: str):
    try:
        run = engine.store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    task = report_tasks.get(run_id)
    status = "idle"
    result: dict[str, str] = {}
    if task:
        if not task.done():
            status = "running"
        elif task.cancelled():
            status = "interrupted"
        elif task.exception():
            status = "failed"
            result["error"] = str(task.exception())
        else:
            path = task.result()
            status = "done"
            result = {"path": str(path), "report": read_report(path)}
    elif run["status"] == "answered":
        latest = engine.latest_report(run_id)
        if latest:
            status = "done"
            result = {"path": str(latest), "report": read_report(latest)}
    return {
        "status": status,
        "assessed": sum("score" in evaluation for evaluation in run["evaluations"].values()),
        "processed": len(run["evaluations"]),
        **result,
    }


@app.post("/api/transcribe/{locale}")
async def transcribe(locale: str, audio: Annotated[UploadFile, File()]):
    try:
        data = await audio.read(20_000_001)
        return {"text": await engine.run_native(speech.transcribe, data, locale)}
    except (
        ValueError,
        RuntimeError,
        OSError,
        wave.Error,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await audio.close()


@app.get("/api/runs/{run_id}/question-audio")
async def question_audio(run_id: str):
    try:
        current = await engine.state(run_id)
        if not current["question"]:
            raise ValueError("No active question")
        data = await engine.run_native(speech.speak, current["question"]["text"], current["locale"])
        return Response(data, media_type="audio/wav")
    except (
        ValueError,
        RuntimeError,
        KeyError,
        OSError,
        wave.Error,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/runs/{run_id}/ceremony-audio/{kind}")
async def ceremony_audio(run_id: str, kind: str):
    try:
        if kind not in {"greeting", "closing"}:
            raise ValueError("Unknown interview utterance")
        current = await engine.state(run_id)
        if not current[kind]:
            raise ValueError("This utterance is not active")
        return Response(
            await engine.run_native(speech.speak, current[kind], current["locale"]), media_type="audio/wav"
        )
    except (
        ValueError,
        RuntimeError,
        KeyError,
        OSError,
        wave.Error,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise HTTPException(400, str(exc)) from exc


HTML = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Interview Simulator</title>
<meta name="interview-token" content="__REQUEST_TOKEN__">
<style>body{font:17px system-ui;max-width:780px;margin:2rem auto;padding:0 1rem;line-height:1.55}
button,select,textarea{font:inherit;margin:.3rem}textarea{width:100%;height:9rem}button{padding:.5rem 1rem}
.error{color:#a00}#report{white-space:pre-wrap}</style>
<h1 id="title">Interview Simulator</h1><p id="intro">Choose a manually prepared opportunity. Practice stays on this device.</p>
<select id="job"></select><select id="locale"><option value="en">English</option><option value="ja">日本語</option>
<option value="zh-Hant">繁體中文 / Mandarin</option></select><select id="flow"><option value="fixed">Fixed practice</option><option value="adaptive">Adaptive question order</option></select><button id="start">Start practice</button>
<p id="history"></p><p id="status"></p><button id="ceremony" hidden></button><h2 id="question"></h2><button id="play" hidden>Play question</button>
<button id="record" hidden>Record answer</button><button id="stop" hidden>Stop recording</button>
<textarea id="answer" placeholder="Confirm or correct your answer before submitting" hidden></textarea>
<button id="submit" hidden>Confirm answer</button><button id="skip" hidden>Skip question</button>
<button id="evaluate" hidden>Generate report</button><pre id="report"></pre>
<script src="/static/app.js" defer></script></html>"""
