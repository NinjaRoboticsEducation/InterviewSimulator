"""Cancellable fictional compatibility checks with a browser heartbeat."""

from __future__ import annotations

import asyncio
import time

from .errors import safe_failure
from .providers import Binding, ProviderError
from .providers.credentials import save_private_json


class ModelChecks:
    def __init__(self, idle_seconds: float = 45, deadline_seconds: float = 600):
        self.jobs: dict[str, dict] = {}
        self.idle_seconds, self.deadline_seconds = idle_seconds, deadline_seconds

    def status(self, job_id: str, heartbeat: bool = True) -> dict:
        job = self.jobs[job_id]
        if heartbeat:
            job["seen"] = time.monotonic()
        return {k: job[k] for k in ("id", "status", "completed", "total", "failure", "result")}

    def start(self, job_id: str, binding: Binding, service) -> dict:
        if job_id in self.jobs:
            if self.jobs[job_id]["binding"] != binding:
                raise ValueError("This model-test request belongs to another selection")
            return self.status(job_id)
        if any(not job["task"].done() for job in self.jobs.values()):
            raise ValueError("Stop the current model test before starting another")
        self.jobs = dict(list(self.jobs.items())[-19:])
        job = self.jobs[job_id] = {
            "id": job_id,
            "binding": binding,
            "status": "running",
            "completed": 0,
            "total": 9 if binding.provider == "ollama" else 1,
            "failure": None,
            "result": None,
            "seen": time.monotonic(),
        }

        def progress(completed, total):
            job.update(completed=completed, total=total)

        async def execute():
            work = asyncio.create_task(service.probe(binding, progress=progress))
            try:
                async with asyncio.timeout(self.deadline_seconds):
                    while not work.done():
                        await asyncio.wait({work}, timeout=min(1, self.idle_seconds))
                        if time.monotonic() - job["seen"] > self.idle_seconds:
                            raise ProviderError(
                                "Model test stopped because the browser disconnected.", code="INTERRUPTED"
                            )
                    job.update(result=work.result(), status="passed")
            except asyncio.CancelledError:
                job.update(status="cancelled", failure=safe_failure(asyncio.CancelledError()))
            except Exception as error:  # noqa: BLE001 - job boundary; persist only content-free diagnostics.
                job.update(status="failed", failure=safe_failure(error))
            finally:
                if not work.done():
                    work.cancel()
                await asyncio.gather(work, return_exceptions=True)
                save_private_json(
                    service.settings.state_root / "last-model-check.json", self.status(job_id, False)
                )

        job["task"] = asyncio.create_task(execute())
        return self.status(job_id)

    async def stop(self, job_id: str) -> dict:
        job = self.jobs[job_id]
        if not job["task"].done():
            job["task"].cancel()
            await asyncio.gather(job["task"], return_exceptions=True)
            if job["status"] == "running":
                job["status"] = "cancelled"
        return self.status(job_id, False)

    async def close(self):
        for job_id in list(self.jobs):
            await self.stop(job_id)
        self.jobs.clear()
