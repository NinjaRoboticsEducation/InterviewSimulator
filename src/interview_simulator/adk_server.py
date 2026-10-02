"""ADK Web bootstrap: cloud keys stay in this process, never in arguments or environment."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from getpass import getpass

from .config import Settings
from .providers import ProviderError, ProviderService

BOOTSTRAP: ProviderService | None = None
CLOUD_ALLOWED = False


def cloud_providers(service: ProviderService) -> set[str]:
    return service.plan.cloud_providers


def serve(settings: Settings, port: int, allow_cloud_text: bool) -> None:
    global BOOTSTRAP, CLOUD_ALLOWED
    import uvicorn
    from click import Abort
    from google.adk.cli.fast_api import get_fast_api_app

    service = ProviderService(settings)
    providers = cloud_providers(service)
    if providers and not allow_cloud_text:
        raise ValueError(
            "This configuration uses cloud text. Review .simulator/model-settings.json and restart "
            "with --allow-cloud-text to permit selected profile/job facts and confirmed answers. Audio remains local."
        )

    async def connect() -> None:
        for provider in sorted(providers - {"ollama"}):
            try:
                service.credentials.get(provider)
            except ProviderError:
                key = getpass(f"{provider} API key (session only, input hidden): ")
                await service.connect(provider, key)
        # Ollama keys are tied to immutable connection profiles, never a generic provider key.
        connections = {
            b.connection
            for b in (
                service.plan.questions,
                service.plan.evaluation,
                service.plan.coaching,
                service.plan.summary,
                service.plan.localization or service.plan.questions,
            )
            if b.provider == "ollama"
        }
        for connection in connections:
            profile = service.ollama.profile(connection)
            if profile["credential"]:
                try:
                    service.credentials.get(profile["credential"])
                except ProviderError:
                    key = getpass(f"Ollama key for {profile['endpoint']} (input hidden): ")
                    service.credentials.set(profile["credential"], key)
        await service.validate(service.plan)

    try:
        asyncio.run(connect())
        BOOTSTRAP, CLOUD_ALLOWED = service, allow_cloud_text

        @asynccontextmanager
        async def lifespan(_app):
            try:
                yield
            finally:
                reports = [t for t in asyncio.all_tasks() if t.get_name() == "interview-report"]
                for task in reports:
                    task.cancel()
                await asyncio.gather(*reports, return_exceptions=True)

        application = get_fast_api_app(
            agents_dir=str(settings.root / "agents"),
            web=True,
            use_local_storage=False,
            host="127.0.0.1",
            bind_host="127.0.0.1",
            port=port,
            reload_agents=False,
            lifespan=lifespan,
        )
        uvicorn.run(
            application,
            host="127.0.0.1",
            port=port,
            timeout_graceful_shutdown=5,
        )
    except (KeyboardInterrupt, Abort):
        # Click wraps the server's normal Ctrl+C shutdown in Abort.
        pass
    finally:
        service.credentials.clear_memory()
        BOOTSTRAP, CLOUD_ALLOWED = None, False
