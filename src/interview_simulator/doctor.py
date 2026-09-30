from __future__ import annotations

import hashlib
import platform
import shutil
import sys
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from .config import Settings
from .speech import Speech


def diagnostics(settings: Settings) -> dict[str, object]:
    model = settings.model_path
    model_info: dict[str, object] = {"configured": bool(model), "exists": bool(model and model.is_file())}
    if model and model.is_file():
        digest = hashlib.sha256()
        with model.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        model_info.update({"name": model.name, "bytes": model.stat().st_size, "sha256": digest.hexdigest()})
    endpoint_ok = False
    try:

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        with build_opener(ProxyHandler({}), NoRedirect()).open(
            settings.model_url.removesuffix("/v1") + "/health", timeout=2
        ) as response:
            endpoint_ok = response.status == 200
    except (OSError, URLError):
        pass
    return {
        "python": sys.version.split()[0],
        "os": platform.system(),
        "architecture": platform.machine(),
        "llama_server": bool(shutil.which("llama-server")),
        "model": model_info,
        "model_endpoint": settings.model_url,
        "endpoint_healthy": endpoint_ok,
        "speech": Speech().capabilities(),
        "primary_profile": "Qwen3.5-9B Q4_K_M",
        "fallback_profile": "Qwen3.5-4B Q4_K_M",
    }
