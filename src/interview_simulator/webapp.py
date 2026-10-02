from __future__ import annotations

import asyncio
import hashlib
import subprocess
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from filelock import FileLock
from interviewwiki.errors import InterviewWikiError
from interviewwiki.util import parse_ref
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .doctor import diagnostics
from .engine import InterviewEngine
from .errors import safe_failure
from .files import reject_links
from .model_checks import ModelChecks
from .providers import Binding, ModelPlan, ProviderError
from .providers.service import HOSTS
from .report_view import report_html, standalone_html, statistics
from .security import REQUEST_TOKEN, LocalRequestMiddleware
from .speech import Speech


@asynccontextmanager
async def lifespan(app):
    lock_path = engine.settings.state_root / "server.lock"
    reject_links(lock_path)
    lease = FileLock(lock_path, timeout=0)
    with lease:
        engine.store.recover_interrupted()
        try:
            yield
        finally:
            await model_checks.close()
            tasks = list(report_tasks.values()) + list(preparation_tasks.values())
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            report_tasks.clear()
            preparation_tasks.clear()
            engine.providers.credentials.clear_memory()


app = FastAPI(title="Interview Simulator", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(LocalRequestMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
engine = InterviewEngine(Settings.load())
speech = Speech()
report_tasks: dict[str, asyncio.Task[Path]] = {}
preparation_tasks: dict[str, asyncio.Task] = {}
model_checks = ModelChecks()


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opportunity: str = Field(min_length=3, max_length=200)
    locale: Literal["en", "ja", "zh-Hant"] = "en"
    mode: Literal["exam"] = "exam"
    flow_mode: Literal["fixed", "adaptive"] = "fixed"
    cloud_consent: bool = False
    request_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{32,36}$")


class AnswerRequest(BaseModel):
    ordinal: int = Field(ge=1, le=10)
    text: str = Field(default="", max_length=6000)
    submission_id: str = Field(min_length=1, max_length=128)
    input_mode: Literal["text", "voice"] = "text"
    skipped: bool = False
    raw_transcript: str | None = Field(default=None, max_length=6000)
    revision: int | None = Field(default=None, ge=0)


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: SecretStr
    remember: bool = False


class EditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=6000)
    submission_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=0)
    skipped: bool = False


class RevisionRequest(BaseModel):
    revision: int = Field(ge=0)


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _error):
    # FastAPI's default error includes input values, which can contain an entered API key.
    return JSONResponse({"detail": "Invalid request. Check the field values and reload if needed."}, 422)


@app.exception_handler(ProviderError)
async def provider_error(_request, error: ProviderError):
    return JSONResponse(
        {"detail": str(error), "failure": error.diagnostic()}, 429 if error.code == "RATE_LIMITED" else 400
    )


@app.get("/api/settings")
def model_settings():
    return {
        "plan": engine.providers.plan.model_dump(),
        "credentials": engine.providers.credentials.status(),
        "local_model": engine.settings.model_name,
        "speech_processing": "local_only",
        "ollama_connections": list(engine.providers.ollama.profiles.values()),
        "workspace_id": hashlib.sha256(str(engine.settings.state_root.resolve()).encode()).hexdigest()[:24],
    }


@app.put("/api/settings")
async def save_model_settings(request: ModelPlan):
    try:
        await engine.providers.save_plan(request)
        return {"saved": True, "plan": request.model_dump()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/providers/{provider}/connect")
async def connect_provider(provider: str, request: KeyRequest):
    try:
        models = await engine.providers.connect(provider, request.key.get_secret_value(), request.remember)
        return {"models": models, "credentials": engine.providers.credentials.status()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/providers/{provider}/models")
async def provider_models(provider: str, refresh: bool = False):
    try:
        return {"models": await engine.providers.discover(provider, refresh)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/providers/{provider}/reconnect")
async def reconnect_provider(provider: str):
    if provider not in HOSTS:
        raise HTTPException(400, "Unknown provider")
    key = await asyncio.to_thread(engine.providers.credentials.reconnect, provider)
    return {"models": await engine.providers.discover(provider, refresh=True, key=key)}


@app.post("/api/providers/{provider}/disconnect")
async def disconnect_provider(provider: str, forget: bool = False):
    if provider not in HOSTS:
        raise HTTPException(400, "Unknown provider")
    await asyncio.to_thread(engine.providers.credentials.disconnect, provider, forget)
    engine.providers._catalog.pop(provider, None)
    return {"disconnected": True}


@app.post("/api/providers/probe")
async def probe_model(binding: Binding):
    try:
        return await engine.providers.probe(binding)
    except ProviderError:
        raise
    except Exception as error:  # noqa: BLE001 - never return SDK/model contents or a non-JSON 500.
        return JSONResponse(
            {
                "detail": "Model test did not pass. Choose another model or provider.",
                "failure": safe_failure(error),
            },
            400,
        )


class ModelCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    binding: Binding


@app.post("/api/model-tests")
async def start_model_check(request: ModelCheckRequest):
    try:
        return model_checks.start(request.request_id, request.binding, engine.providers)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/model-tests/{job_id}")
async def model_check_status(job_id: str):
    try:
        return model_checks.status(job_id)
    except KeyError as error:
        raise HTTPException(404, "Model test not found. Start another test.") from error


@app.delete("/api/model-tests/{job_id}")
async def stop_model_check(job_id: str):
    try:
        return await model_checks.stop(job_id)
    except KeyError as error:
        raise HTTPException(404, "Model test not found") from error


from .providers.ollama import ConnectionRequest


@app.post("/api/ollama/connections")
async def connect_ollama(request: ConnectionRequest):
    try:
        return await engine.providers.ollama.connect(request)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/ollama/{connection}/models")
async def ollama_models(connection: str):
    try:
        return {"models": await engine.providers.ollama.discover(connection)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/ollama/inspect")
async def inspect_ollama(binding: Binding):
    try:
        return await engine.providers.ollama.inspect(binding, enforce_locality=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/ollama/{connection}/reconnect")
async def reconnect_ollama(connection: str, request: KeyRequest | None = None):
    profile = engine.providers.ollama.profile(connection)
    credential = profile["credential"]
    if not credential:
        if request:
            raise HTTPException(400, "Create a new connection to add a destination-bound key")
    elif request:
        await asyncio.to_thread(
            engine.providers.credentials.set, credential, request.key.get_secret_value(), request.remember
        )
    else:
        await asyncio.to_thread(engine.providers.credentials.reconnect, credential)
    engine.providers.ollama.disconnected.discard(connection)
    return {"models": await engine.providers.ollama.discover(connection)}


@app.post("/api/ollama/{connection}/disconnect")
async def disconnect_ollama(connection: str, forget: bool = False):
    profile = engine.providers.ollama.profile(connection)
    if profile["credential"]:
        await asyncio.to_thread(engine.providers.credentials.disconnect, profile["credential"], forget)
    engine.providers.ollama.disconnected.add(connection)
    return {"disconnected": True}


class RecoveryRequest(RevisionRequest):
    request_id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")


class ReportRevisionRequest(RecoveryRequest):
    plan: ModelPlan
    cloud_consent: bool = False


@app.get("/api/runs")
def list_runs():
    return {"runs": engine.store.list_runs()}


@app.get("/api/runs/{run_id}/view")
def view_run(run_id: str):
    try:
        saved = engine.store.get_run(run_id)
        return {
            **engine.review(run_id),
            "locale": saved["locale"],
            "opportunity": saved["opportunity"],
            "flow_mode": saved["flow_mode"],
            "answered": len(saved["answers"]),
            "question": None,
            "greeting": None,
            "closing": None,
            "editable": False,
            "report_error": saved.get("report_error"),
            "preparation_error": saved.get("preparation_error"),
        }
    except KeyError as exc:
        raise HTTPException(404, "Interview not found") from exc


@app.post("/api/runs/{run_id}/preparation/retry")
async def retry_preparation(run_id: str, baseline: bool = False):
    try:
        return await engine.retry_preparation(run_id, baseline)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/runs/{run_id}/report/allowance")
def report_allowance(run_id: str, request: RecoveryRequest):
    try:
        engine.store.grant_recovery(run_id, request.request_id, request.revision)
        return {"revision": engine.store.get_run(run_id)["revision"]}
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/runs/{run_id}/report/revision")
async def revise_report(run_id: str, request: ReportRevisionRequest):
    try:
        task = report_tasks.get(run_id)
        if task and not task.done():
            raise ValueError("Stop the current report worker first")
        state = await engine.revise_report(
            run_id, request.plan, request.revision, request.request_id, request.cloud_consent
        )
        report_tasks.pop(run_id, None)
        return state
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


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


@app.get("/api/speech")
def speech_status():
    # A fast readiness check: do not hash a multi-gigabyte LLM to enable audio controls.
    return speech.capabilities()


@app.post("/api/runs")
async def start(request: StartRequest):
    try:
        plan = engine.providers.plan
        cloud = bool(plan.cloud_providers)
        if cloud and not request.cloud_consent:
            raise ValueError(
                "Confirm that selected job/profile facts and answer text may be sent to your providers. Audio stays local."
            )
        if request.request_id and request.request_id in preparation_tasks:
            raise HTTPException(409, "Preparation is already running")
        task = asyncio.create_task(
            engine.start(
                request.opportunity,
                request.locale,
                request.mode,
                request.flow_mode,
                request.cloud_consent,
                request.request_id,
            )
        )
        if request.request_id:
            preparation_tasks[request.request_id] = task
        try:
            return await task
        except asyncio.CancelledError:
            return JSONResponse(
                {"detail": "Preparation stopped.", "failure": safe_failure(asyncio.CancelledError())}, 409
            )
        finally:
            if request.request_id:
                preparation_tasks.pop(request.request_id, None)
    except (ValueError, FileNotFoundError, KeyError, InterviewWikiError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/preparations/{request_id}/cancel")
async def cancel_preparation(request_id: str):
    task = preparation_tasks.get(request_id)
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    run_id = engine.store.request_run(request_id)
    if run_id:
        saved = engine.store.get_run(run_id)
        if saved["status"] not in {"cancelled", "answered"}:
            await engine.action(run_id, "cancel", saved["revision"])
    return {"cancelled": True}


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
            request.revision,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/runs/{run_id}/review")
def review_answers(run_id: str):
    try:
        return engine.review(run_id)
    except KeyError as exc:
        raise HTTPException(404, "Interview not found") from exc


@app.put("/api/runs/{run_id}/answers/{ordinal}")
async def edit_answer(run_id: str, ordinal: int, request: EditRequest):
    try:
        return await engine.edit(
            run_id, ordinal, request.text, request.submission_id, request.revision, request.skipped
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/runs/{run_id}/actions/{action}")
async def interview_action(run_id: str, action: str, request: RevisionRequest):
    try:
        return await engine.action(run_id, action, request.revision)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


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
async def start_report(run_id: str, request: RevisionRequest | None = None):
    try:
        run = engine.store.get_run(run_id)
        if len(run["answers"]) != 10:
            raise ValueError("Complete or skip all ten questions first")
        engine.store.lock_scoring(run_id, request.revision if request else None)
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
        elif (failure := task.exception()) is not None:
            status = "failed"
            result["error"] = safe_failure(failure)["message"]
        else:
            path = task.result()
            status = "done"
            result = {"path": str(path), "report": read_report(path)}
    elif run["status"] == "answered":
        try:
            latest = engine.latest_report(run_id)
            if latest:
                status = "done"
                result = {"path": str(latest), "report": read_report(latest)}
        except (ValueError, OSError):
            status = "failed"
            result["error"] = (
                "Saved report export needs repair. Resume report work; answers and scores remain saved."
            )
    return {
        "status": status,
        "report_state": run.get("report_state", "idle"),
        "assessed": sum("score" in evaluation for evaluation in run["evaluations"].values()),
        "processed": len(run["evaluations"]),
        "failure": run.get("report_error"),
        "assessment_version": run.get("assessment_version", 0),
        **result,
        **(
            {"html": report_html(result["report"], run), "statistics": statistics(run)}
            if "report" in result
            else {}
        ),
    }


@app.post("/api/runs/{run_id}/report/stop")
async def stop_report(run_id: str):
    try:
        run = engine.store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, "Interview not found") from exc
    task = report_tasks.get(run_id)
    if not task or task.done():
        return {"stopped": False, "message": "No report is running; saved state is unchanged."}
    task.cancel()
    # Wait until the worker releases its lock before allowing a retry. Only the
    # scoring worker owns report-state transitions, including interruption.
    await asyncio.gather(task, return_exceptions=True)
    if run.get("report_state") == "running":
        engine.store.report_state(run_id, "interrupted")
    return {"stopped": True, "message": "Completed scores remain saved; answers remain locked."}


@app.get("/api/runs/{run_id}/report/download")
def download_report(run_id: str, format: Literal["md", "html"] = "md"):
    try:
        path = engine.latest_report(run_id)
        if not path:
            raise ValueError("No saved report yet")
        text = read_report(path)
        if format == "html":
            css = (Path(__file__).parent / "static/style.css").read_text(encoding="utf-8")
            text = standalone_html(text, engine.store.get_run(run_id), css)
        return Response(
            text,
            media_type="text/html" if format == "html" else "text/markdown",
            headers={"Content-Disposition": f'attachment; filename="interview-report.{format}"'},
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc


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
async def question_audio(run_id: str, ordinal: int | None = None):
    try:
        if ordinal is not None:
            saved = engine.store.get_run(run_id)
            if not 1 <= ordinal <= len(saved["answers"]):
                raise ValueError("Choose a confirmed earlier question")
            text, locale = saved["questions"][ordinal - 1]["text"], saved["locale"]
        else:
            current = await engine.state(run_id)
            if not current["question"]:
                raise ValueError("No active question")
            text, locale = current["question"]["text"], current["locale"]
        data = await engine.run_native(speech.speak, text, locale)
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


HTML = (Path(__file__).parent / "static/index.html").read_text(encoding="utf-8")
