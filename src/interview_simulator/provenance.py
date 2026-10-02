"""Identify the local model actually advertised by a single-model llama.cpp server."""

from __future__ import annotations

import asyncio
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .files import reject_links


@lru_cache(maxsize=4)
def _digest(path: Path, signature: tuple[int, int, int, int]) -> str:
    reject_links(path)
    with path.open("rb") as stream:
        value = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    stat = path.stat()
    if signature != (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns):
        raise ValueError("GGUF file changed during fingerprinting")
    return value


async def model_identity(settings: Settings) -> dict[str, Any]:
    path = settings.model_path
    if path is None or not path.is_file():
        raise ValueError("Set INTERVIEW_SIMULATOR_GGUF to the GGUF file loaded by llama.cpp")
    reject_links(path)
    url = settings.model_url.removesuffix("/v1") + "/props"
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {settings.model_api_key}"})
        response.raise_for_status()
        props = response.json()
    advertised = props.get("model_path")
    if not isinstance(advertised, str) or not Path(advertised).is_file():
        raise ValueError("llama.cpp did not disclose a local model_path in /props")
    advertised_path = Path(advertised)
    reject_links(advertised_path)
    stat = path.stat()
    signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    digest = await asyncio.to_thread(_digest, path, signature)
    if not advertised_path.samefile(path):
        loaded_stat = advertised_path.stat()
        loaded_signature = (
            loaded_stat.st_ino,
            loaded_stat.st_size,
            loaded_stat.st_mtime_ns,
            loaded_stat.st_ctime_ns,
        )
        loaded_digest = await asyncio.to_thread(_digest, advertised_path, loaded_signature)
        if loaded_digest != digest:
            raise ValueError("The loaded llama.cpp model differs from INTERVIEW_SIMULATOR_GGUF")
    return {
        "model_alias": settings.model_name,
        "gguf_file": path.name,
        "gguf_sha256": digest,
        "source": "llama.cpp /props loaded file fingerprint matched the configured local file",
    }
