"""Native text-only Ollama transport with immutable destination/credential profiles."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..errors import InputBudgetError
from ..files import reject_links
from .base import Binding, ProviderError
from .credentials import save_private_json

QUALIFICATION_VERSION = "ollama-tasks-v2"


class ConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern=r"^(local|cloud)$")
    endpoint: str = "http://127.0.0.1:11434"
    key: SecretStr | None = None
    remember: bool = False
    context_tokens: int = Field(default=4096, ge=4096, le=16384)


def normalize_endpoint(mode: str, endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Use a plain loopback address or the official Ollama HTTPS address")
    if mode == "cloud":
        if parsed.scheme != "https" or parsed.hostname != "ollama.com" or parsed.port not in {None, 443}:
            raise ValueError("Direct cloud connections use https://ollama.com only")
        return "https://ollama.com"
    if mode != "local" or parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Local Ollama must use an HTTP loopback address on this computer")
    host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
    port = parsed.port or 11434
    if not 1 <= port <= 65535:
        raise ValueError("Invalid local port")
    return f"http://{host}:{port}"


class Ollama:
    def __init__(self, service):
        self.service = service
        self.path = service.settings.state_root / "ollama-profiles.json"
        reject_links(self.path)
        self.profiles = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.cooldowns: dict[str, float] = {}
        self.disconnected: set[str] = set()

    def profile(self, connection: str | None) -> dict:
        if not connection or connection not in self.profiles:
            raise ValueError("Choose an existing Ollama connection")
        profile = self.profiles[connection]
        if normalize_endpoint(profile["mode"], profile["endpoint"]) != profile["endpoint"]:
            raise ValueError("Invalid saved Ollama destination")
        return profile

    async def request(self, connection: str, method: str, path: str, body=None) -> dict:
        import time

        from .service import retry_delay

        profile = self.profile(connection)
        if connection in self.disconnected:
            raise ProviderError(
                "Reconnect this Ollama profile before using it.",
                code="AUTHENTICATION_FAILED",
                dispatch="not_sent",
            )
        if path not in {"/api/version", "/api/tags", "/api/show", "/api/ps", "/api/chat"}:
            raise ValueError("Invalid Ollama API path")
        remaining = self.cooldowns.get(connection, 0) - time.time()
        if remaining > 0:
            raise ProviderError(
                "Ollama is waiting after a rate limit.",
                code="RATE_LIMITED",
                retry_after=remaining,
                dispatch="not_sent",
            )
        key = (
            await asyncio.to_thread(self.service.credentials.get, profile["credential"])
            if profile["credential"]
            else None
        )
        headers = {"Authorization": "Bearer " + key} if key else {}
        try:
            async with (
                asyncio.timeout(190 if path == "/api/chat" else 20),
                httpx.AsyncClient(
                    transport=self.service.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(180 if path == "/api/chat" else 15, connect=5),
                ) as client,
                client.stream(method, profile["endpoint"] + path, json=body, headers=headers) as response,
            ):
                if response.status_code == 429:
                    delay = retry_delay(response.headers.get("retry-after"))
                    self.cooldowns[connection] = time.time() + (delay if delay is not None else 60)
                    raise ProviderError(
                        "Ollama quota or rate limit reached. Check the selected account.",
                        code="RATE_LIMITED",
                        retry_after=delay,
                        http_status=429,
                        dispatch="sent",
                    )
                if response.status_code != 200:
                    raise ProviderError(
                        "Ollama request failed. Check daemon sign-in, model availability or account access.",
                        code="AUTHENTICATION_FAILED"
                        if response.status_code in {401, 403}
                        else "TEMPORARY_UNAVAILABLE",
                        http_status=response.status_code,
                        dispatch="sent",
                    )
                content = bytearray()
                async for block in response.aiter_bytes():
                    content.extend(block)
                    if len(content) > 8_000_000:
                        raise ProviderError("Ollama response exceeded the safety limit")
                data = json.loads(content)
                if not isinstance(data, dict) or data.get("error"):
                    raise ProviderError("Ollama returned an error or an invalid object", dispatch="sent")
                if key and key in json.dumps(data):
                    raise ProviderError("Ollama returned unsafe output")
                return data
        except ProviderError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderError(
                "Ollama timed out. Resume explicitly; a cloud request may have been billed.",
                code="TIMEOUT",
                dispatch="unknown",
            ) from None
        except Exception:  # noqa: BLE001 - suppress upstream content and credentials
            raise ProviderError("Cannot reach or read Ollama. Check this connection.") from None

    async def connect(self, request: ConnectionRequest) -> dict:
        endpoint = normalize_endpoint(request.mode, request.endpoint)
        key = request.key.get_secret_value() if request.key else None
        if request.mode == "cloud" and not key:
            raise ValueError("An API key is required for direct Ollama cloud access")
        connection = uuid.uuid4().hex
        credential = "ollama-" + connection if key else None
        profile = {
            "id": connection,
            "mode": request.mode,
            "endpoint": endpoint,
            "context_tokens": request.context_tokens,
            "credential": credential,
            "qualified": {},
        }
        # A failed connection is not persisted. Keys remain bound to this immutable destination.
        self.profiles[connection] = profile
        try:
            if key:
                await asyncio.to_thread(self.service.credentials.set, credential, key, request.remember)
            if request.mode == "local":
                await self.request(connection, "GET", "/api/version")
            models = await self.discover(connection)
            save_private_json(self.path, self.profiles)
            return {"connection": profile, "models": models}
        except BaseException:
            self.profiles.pop(connection, None)
            if credential:
                await asyncio.to_thread(self.service.credentials.disconnect, credential, request.remember)
            raise

    async def discover(self, connection: str) -> list[dict]:
        profile = self.profile(connection)
        data = await self.request(connection, "GET", "/api/tags")
        entries = data.get("models")
        if not isinstance(entries, list) or len(entries) > 5000:
            raise ProviderError("Invalid Ollama model catalog")
        result = []
        for entry in entries:
            name = entry.get("name", entry.get("model")) if isinstance(entry, dict) else None
            if not isinstance(name, str) or not re.fullmatch(r"[\w./:-]{1,150}", name):
                continue
            remote = (
                entry.get("remote_host")
                or entry.get("remote_model")
                or name.endswith(":cloud")
                or "-cloud" in name
            )
            locality = "cloud" if profile["mode"] == "cloud" or remote else "local"
            qualified = profile["qualified"].get(name, {}).get("version") == QUALIFICATION_VERSION
            result.append(
                {
                    "id": name,
                    "name": name,
                    "compatible": False,
                    "tested": qualified,
                    "locality": locality,
                    "digest": entry.get("digest"),
                    "reason": "Verify capabilities and locality; cloud models require the representative task check.",
                }
            )
        return result

    async def inspect(self, binding: Binding, enforce_locality: bool = True) -> dict:
        profile = self.profile(binding.connection)
        assert binding.connection is not None
        models = await self.discover(binding.connection)
        match = next((m for m in models if m["id"] == binding.model), None)
        if match is None:
            raise ValueError("Choose an Ollama model from this connection's catalog")
        details = (
            {}
            if profile["mode"] == "cloud"
            else await self.request(binding.connection, "POST", "/api/show", {"model": binding.model})
        )
        if details.get("remote_host") and urlsplit(details["remote_host"]).hostname != "ollama.com":
            raise ValueError("This model has an unsupported or ambiguous remote destination")
        remote = details.get("remote_host") or details.get("remote_model")
        locality = "cloud" if remote or match["locality"] == "cloud" else "local"
        if enforce_locality and binding.locality != locality:
            raise ValueError(
                "Model locality changed. Review the connection and cloud consent before continuing"
            )
        caps = details.get("capabilities", [])
        if locality == "local" and ("completion" not in caps or not match.get("digest")):
            raise ValueError("Local completion capability and model digest could not be verified")
        digest = match.get("digest") or binding.model
        return {
            **match,
            "locality": locality,
            "capabilities": caps,
            "thinking": details.get("thinking"),
            "digest": digest,
            "quantization": details.get("details", {}).get("quantization_level"),
            "context_tokens": profile["context_tokens"],
            "structured_output": "schema" if locality == "local" else "application-validated JSON",
        }

    async def validate(self, binding: Binding) -> dict:
        info = await self.inspect(binding)
        qualified = self.profile(binding.connection)["qualified"].get(binding.model, {})
        if info["locality"] == "cloud" and (
            qualified.get("version") != QUALIFICATION_VERSION or qualified.get("digest") != info["digest"]
        ):
            raise ValueError(
                "Ollama cloud model requires a representative multilingual task check before use"
            )
        thinking = info.get("thinking") or {}
        if binding.reasoning and binding.reasoning not in thinking.get("values", []):
            raise ProviderError(
                "This Ollama model does not advertise this thinking setting. Select Provider default.",
                code="MODEL_CONFIGURATION",
                dispatch="not_sent",
            )
        return info

    async def generate(
        self, binding: Binding, instruction: str, prompt: str, schema: dict
    ) -> tuple[str, dict]:
        info = await self.inspect(binding)
        system = instruction + " Return one JSON object only."
        if info["locality"] == "cloud":
            system += " Required schema: " + json.dumps(schema, separators=(",", ":"))
        body: dict[str, Any] = {
            "model": binding.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"num_predict": binding.max_output_tokens, "temperature": 0.2},
        }
        if info["locality"] == "local":
            context = info["context_tokens"]
            # No tokenizer endpoint: use UTF-8 bytes as a conservative upper bound.
            if len((system + prompt).encode()) + binding.max_output_tokens + 512 > context:
                raise InputBudgetError(
                    "Ollama's conservative context budget is too small. Review the local connection context setting."
                )
            body["format"] = schema
            body["options"]["num_ctx"] = context
        thinking = info.get("thinking") or {}
        values = thinking.get("values", [])
        if binding.reasoning:
            if binding.reasoning not in values:
                raise ProviderError(
                    "This Ollama model does not advertise this thinking setting. Select Provider default.",
                    code="MODEL_CONFIGURATION",
                    dispatch="not_sent",
                )
            body["think"] = binding.reasoning
        elif False in values:
            body["think"] = False
        assert binding.connection is not None
        data = await self.request(binding.connection, "POST", "/api/chat", body)
        if data.get("done") is not True or data.get("done_reason") in {"length", "max_tokens"}:
            raise ProviderError(
                "Ollama output was incomplete. Review the output allowance.",
                code="OUTPUT_LIMIT",
                dispatch="sent",
            )
        message = data.get("message", {})
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 100000:
            raise ProviderError("Ollama returned no usable text", dispatch="sent")
        loaded_context = None
        if info["locality"] == "local":
            try:
                loaded = await self.request(binding.connection, "GET", "/api/ps")
                for model in loaded.get("models", []):
                    if model.get("name", model.get("model")) == binding.model:
                        value = model.get("context_length")
                        if type(value) is int and value > 0:
                            loaded_context = value
            except ProviderError:
                pass  # Older servers may not expose loaded context; never invent it.
            if loaded_context is not None and loaded_context < info["context_tokens"]:
                raise ProviderError(
                    "Ollama loaded a smaller context than requested. Review the connection.",
                    code="INPUT_TOO_LARGE",
                    dispatch="sent",
                )
        return text, {
            "provider": "ollama",
            "requested_model": binding.model,
            "returned_model": data["model"]
            if isinstance(data.get("model"), str) and re.fullmatch(r"[\w./:-]{1,150}", data["model"])
            else binding.model,
            "connection": binding.connection,
            "locality": info["locality"],
            "model_digest": info["digest"],
            "quantization": info.get("quantization"),
            "context_tokens": info["context_tokens"],
            "loaded_context_tokens": loaded_context,
            "structured_output": info["structured_output"],
            "usage": {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
            "estimated_usd": None,
        }
