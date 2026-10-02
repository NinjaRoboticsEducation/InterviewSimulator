from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from ..config import Settings
from ..files import reject_links
from .base import KNOWN, TASKS, Binding, ModelPlan, ProviderError, estimated_cost
from .credentials import Credentials, save_private_json

HOSTS = {
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


def retry_delay(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = (
            float(value)
            if re.fullmatch(r"\d+(\.\d+)?", value)
            else (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        )
        return min(86400, max(0, seconds))
    except (ValueError, TypeError, OverflowError):
        return None


class ProviderService:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.credentials = Credentials(settings.state_root)
        self.path = settings.state_root / "model-settings.json"
        reject_links(self.path)
        self.plan = (
            ModelPlan.model_validate_json(self.path.read_text())
            if self.path.exists()
            else ModelPlan().model_copy(
                update={
                    task: Binding(
                        model=settings.model_name,
                        max_output_tokens=getattr(ModelPlan(), task).max_output_tokens,
                    )
                    for task in TASKS
                }
            )
        )
        self.transport = transport
        self._catalog: dict[str, tuple[float, list[dict]]] = {}
        self._verified: set[tuple[str, str]] = set()
        self.last_call: dict[str, Any] = {}
        self._cooldowns: dict[str, float] = {}
        from .ollama import Ollama

        self.ollama = Ollama(self)

    async def _request(
        self,
        provider: str,
        method: str,
        path: str,
        key: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> tuple[dict, dict]:
        # Only fixed provider hosts are accepted; no browser-configurable base URLs.
        if provider not in HOSTS or not path.startswith("/") or ".." in path:
            raise ProviderError("Invalid provider request")
        remaining = self._cooldowns.get(provider, 0) - time.time()
        if remaining > 0:
            raise ProviderError(
                "Provider is waiting after a rate limit. Resume after the displayed delay.",
                code="RATE_LIMITED",
                retry_after=remaining,
                dispatch="not_sent",
                http_status=429,
            )
        headers = {"Content-Type": "application/json"}
        if provider == "google":
            headers["x-goog-api-key"] = key
        elif provider == "openai":
            headers["Authorization"] = "Bearer " + key
        else:
            headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        try:
            async with asyncio.timeout(180):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(120, connect=10),
                ) as client:
                    for attempt in range(2):
                        async with client.stream(
                            method, HOSTS[provider] + path, headers=headers, json=body, params=params
                        ) as response:
                            if response.status_code == 429:
                                delay = retry_delay(response.headers.get("retry-after"))
                                self._cooldowns[provider] = time.time() + (delay if delay is not None else 60)
                                raise ProviderError(
                                    "Provider quota or rate limit reached. Wait and check your account.",
                                    code="RATE_LIMITED",
                                    retry_after=delay,
                                    http_status=429,
                                    dispatch="sent",
                                )
                            if response.status_code in {502, 503, 504} and attempt == 0:
                                delay = response.headers.get("retry-after", "1")
                                seconds = retry_delay(delay) or 1
                                if seconds > 5:
                                    raise ProviderError(
                                        "Provider temporarily unavailable. Resume after the displayed delay.",
                                        code="TEMPORARY_UNAVAILABLE",
                                        retry_after=seconds,
                                        http_status=response.status_code,
                                        dispatch="sent",
                                    )
                                await asyncio.sleep(seconds)
                                continue
                            if response.status_code != 200:
                                messages = {
                                    401: "Key rejected. Replace the selected provider key.",
                                    403: "Provider access denied. Check key permissions and billing.",
                                    429: "Provider quota or rate limit reached. Wait and check your account.",
                                }
                                raise ProviderError(
                                    messages.get(
                                        response.status_code,
                                        f"Provider request failed ({response.status_code}). Check model compatibility and account status.",
                                    ),
                                    code="AUTHENTICATION_FAILED"
                                    if response.status_code in {401, 403}
                                    else "TEMPORARY_UNAVAILABLE",
                                    http_status=response.status_code,
                                    dispatch="sent",
                                )
                            data = bytearray()
                            async for block in response.aiter_bytes():
                                data.extend(block)
                                if len(data) > 8_000_000:
                                    raise ProviderError("Provider response exceeded the safety limit")
                            parsed = json.loads(data)
                            if not isinstance(parsed, dict):
                                raise ProviderError("Provider returned an invalid object")
                            request_id = response.headers.get(
                                "request-id", response.headers.get("x-request-id", "")
                            )
                            meta = (
                                {"request_id": request_id}
                                if re.fullmatch(r"[\w-]{1,150}", request_id) and key not in request_id
                                else {}
                            )
                            meta["transport_attempts"] = attempt + 1
                            return parsed, meta
        except ProviderError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderError(
                "Provider timed out. The request may have been billed; retry explicitly.",
                code="TIMEOUT",
                dispatch="unknown",
            ) from None
        except Exception:  # noqa: BLE001 - never leak upstream credentials or vault diagnostics
            # Do not expose upstream bodies, credentials, SDK exception text, or candidate data.
            raise ProviderError(
                "Could not reach or read the provider. Check your network and reconnect."
            ) from None
        raise ProviderError("Provider request did not complete")

    async def connect(self, provider: str, key: str, remember: bool = False) -> list[dict]:
        if provider not in HOSTS or not 8 <= len(key) <= 512 or any(c.isspace() for c in key):
            raise ValueError("Enter a cloud provider key without spaces")
        models = await self.discover(provider, refresh=True, key=key)
        await asyncio.to_thread(self.credentials.set, provider, key, remember)
        return models

    async def discover(self, provider: str, refresh: bool = False, key: str | None = None) -> list[dict]:
        if provider == "local":
            return [
                {
                    "id": self.settings.model_name,
                    "name": self.settings.model_name,
                    "compatible": True,
                    "reason": "Configured llama.cpp alias; verified at scoring.",
                }
            ]
        if provider not in HOSTS:
            raise ValueError("Unknown provider")
        cached = self._catalog.get(provider)
        if not refresh and key is None and cached and time.monotonic() - cached[0] < 900:
            return cached[1]
        secret = key or await asyncio.to_thread(self.credentials.get, provider)
        if not isinstance(secret, str):
            raise ProviderError("Reconnect this provider")
        params: dict[str, Any] = {"pageSize": 1000} if provider == "google" else {}
        models = []
        seen_pages = set()
        for _ in range(20):
            data, _metadata = await self._request(provider, "GET", "/models", secret, params=params)
            entries = data.get("models" if provider == "google" else "data", [])
            if not isinstance(entries, list):
                raise ProviderError("Provider model catalog is invalid")
            for item in entries:
                if not isinstance(item, dict):
                    continue
                model_id = item.get("name" if provider == "google" else "id", "")
                if provider == "google" and isinstance(model_id, str):
                    model_id = model_id.removeprefix("models/")
                if not isinstance(model_id, str) or not re.fullmatch(r"[\w./:-]{1,150}", model_id):
                    continue
                if secret in model_id:
                    continue
                known = bool(KNOWN.get(provider, {}).get(model_id, {}).get("structured"))
                caps = item.get("capabilities") or {}
                structure = caps.get("structured_outputs") if isinstance(caps, dict) else None
                structured = isinstance(structure, dict) and structure.get("supported") is True
                verified = (provider, model_id) in self._verified
                supported = known or structured or verified
                methods = item.get("supportedGenerationMethods")
                if provider == "google" and (
                    not isinstance(methods, list) or "generateContent" not in methods
                ):
                    supported = False
                display = item.get("displayName", item.get("display_name", model_id))
                models.append(
                    {
                        "id": model_id,
                        "name": display[:200]
                        if isinstance(display, str) and secret not in display
                        else model_id,
                        "compatible": supported,
                        "tested": verified,
                        "reason": "Synthetic schema check passed."
                        if verified
                        else "Documented structured output; test this model before first use."
                        if supported
                        else "Compatibility unknown. Run a synthetic model check.",
                        "checked_at": "2026-10-01" if known else None,
                    }
                )
            if len(models) > 5000:
                raise ProviderError("Model catalog exceeded the safety limit")
            cursor = (
                data.get("nextPageToken")
                if provider == "google"
                else (data.get("last_id") if data.get("has_more") else None)
            )
            if not cursor:
                break
            if not isinstance(cursor, str) or len(cursor) > 1000 or cursor in seen_pages:
                raise ProviderError("Invalid provider pagination")
            seen_pages.add(cursor)
            params["pageToken" if provider == "google" else "after_id"] = cursor
        else:
            raise ProviderError("Model catalog pagination exceeded the safety limit")
        unique = {item["id"]: item for item in models}
        result = sorted(unique.values(), key=lambda m: (not m["compatible"], m["id"]))
        self._catalog[provider] = (time.monotonic(), result)
        return result

    async def validate(self, plan: ModelPlan) -> None:
        for task in (*TASKS, "localization"):
            if (task == "questions" and not plan.generate_questions) or (
                task == "summary" and not plan.generate_summary
            ):
                continue
            binding = (plan.localization or plan.questions) if task == "localization" else getattr(plan, task)
            if binding.provider == "local":
                if binding.model != self.settings.model_name:
                    raise ValueError("Select the configured local model alias")
                continue
            if binding.provider == "ollama":
                await self.ollama.validate(binding)
                continue
            # Credential lookup is required even when discovery metadata is cached.
            await asyncio.to_thread(self.credentials.get, binding.provider)
            matches = [m for m in await self.discover(binding.provider) if m["id"] == binding.model]
            if not matches or not matches[0]["compatible"]:
                raise ValueError(f"{task}: select a discovered compatible model, or test its schema support")

    async def save_plan(self, plan: ModelPlan) -> None:
        await self.validate(plan)
        save_private_json(self.path, plan.model_dump())
        self.plan = plan

    async def probe(self, binding: Binding, progress=None) -> dict:
        if binding.provider == "local":
            raise ValueError("Use local model diagnostics and qualification instead")
        if binding.provider == "ollama":
            return await self.probe_ollama(binding, progress)
        models = await self.discover(binding.provider)
        if binding.model not in {m["id"] for m in models}:
            raise ValueError("Choose a model from this provider's catalog")
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        text = await self.generate(
            binding.model_copy(update={"max_output_tokens": 256}),
            "Return JSON with ok set to true.",
            "Synthetic compatibility test",
            schema,
        )
        if json.loads(text) != {"ok": True}:
            raise ProviderError("Model did not pass the structured-output test")
        self._verified.add((binding.provider, binding.model))
        self._catalog.pop(binding.provider, None)
        if progress:
            progress(1, 1)
        return {"passed": True, "usage": self.last_call.get("usage", {})}

    async def probe_ollama(self, binding: Binding, progress=None) -> dict:
        """Representative fictional task checks; never send candidate information."""
        from ..adk_runtime import COACHING_SCHEMA, EVALUATION_SCHEMA
        from ..evaluation import parse_json_object, validate_coaching, validate_evaluation
        from ..localization import validate_text
        from .ollama import QUALIFICATION_VERSION

        info = await self.ollama.inspect(binding)
        completed = 0

        def checked():
            nonlocal completed
            completed += 1
            if progress:
                progress(completed, 9)

        profile = self.ollama.profile(binding.connection)
        if binding.model in profile["qualified"]:
            profile["qualified"].pop(binding.model)
            save_private_json(self.ollama.path, self.ollama.profiles)
        for locale, answer in {
            "en": "I built a test service.",
            "ja": "テスト用サービスを開発しました。",
            "zh-Hant": "我開發了測試服務。",
        }.items():
            prompt = json.dumps(
                {
                    "locale": locale,
                    "question": answer,
                    "answer": answer,
                    "answer_spans": {"s1": answer},
                    "confirmed_facts": {"f": answer},
                },
                ensure_ascii=False,
            )
            test = binding.model_copy(update={"max_output_tokens": 1024})
            raw = parse_json_object(
                await self.generate(
                    test,
                    "Assess this fictional answer. Five scores 0..4; cite s1 and f; feedback in locale.",
                    prompt,
                    EVALUATION_SCHEMA,
                )
            )
            if raw.pop("quote_span_id", None) != "s1":
                raise ValueError("Ollama failed evidence selection")
            raw["quote"] = answer
            validate_evaluation(raw, answer, {"f"}, "portfolio", locale)
            checked()
            raw = parse_json_object(
                await self.generate(
                    test,
                    "Coach this fictional candidate. Write all prose in locale. Use two example clauses. First: "
                    "kind=fact, fact_ids=[f], a minimal first-person paraphrase of confirmed fact f. "
                    "Do not infer outcomes, leadership, improvements or other achievements from doing the task. "
                    "Add one motivation clause with empty fact_ids expressing interest in discussing this contribution, without inventing past values or achievements. Top-level fact_ids=[f]. Keep why_it_works, outline and "
                    "next_action to one brief sentence each; advice may suggest future verification but no past claims.",
                    prompt,
                    COACHING_SCHEMA,
                )
            )
            validate_coaching(raw, {"f": answer}, {"category": "portfolio", "locale": locale})
            if not {"fact", "motivation"} <= {c["kind"] for c in raw.get("example_clauses", [])}:
                raise ValueError("Ollama qualification requires supported experience and natural intent")
            checked()
        for locale in ("ja", "zh-Hant"):
            schema = {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            }
            raw = parse_json_object(
                await self.generate(
                    binding.model_copy(update={"max_output_tokens": 512}),
                    "Translate the question faithfully into locale. Preserve numbers, names and negation.",
                    json.dumps(
                        {
                            "locale": locale,
                            "question": "I supported 2 team projects, not led them. What did I contribute?",
                        }
                    ),
                    schema,
                )
            )
            validate_text(
                raw.get("text"), locale, "I supported 2 team projects, not led them. What did I contribute?"
            )
            checked()
        schema = {
            "type": "object",
            "properties": {"supported": {"type": "boolean"}},
            "required": ["supported"],
            "additionalProperties": False,
        }
        negative = parse_json_object(
            await self.generate(
                binding.model_copy(update={"max_output_tokens": 256}),
                "Audit fictional claims. Return supported=true only if the example is entailed by the facts; "
                "never infer results from performing a task.",
                json.dumps(
                    {
                        "facts": {"f": "I wrote tests as a team member; I did not lead."},
                        "example": "I led the project and reduced defects by 40%.",
                    }
                ),
                schema,
            )
        )
        if negative != {"supported": False}:
            raise ValueError("Ollama failed the unsupported-claim rejection check")
        checked()
        profile = self.ollama.profile(binding.connection)
        profile["qualified"][binding.model] = {"version": QUALIFICATION_VERSION, "digest": info["digest"]}
        save_private_json(self.ollama.path, self.ollama.profiles)
        return {"passed": True, "checks": 9, "capability": info["structured_output"]}

    async def generate(self, binding: Binding, instruction: str, prompt: str, schema: dict) -> str:
        provider = binding.provider
        if provider == "ollama":
            text, self.last_call = await self.ollama.generate(binding, instruction, prompt, schema)
            from jsonschema import validate

            from ..evaluation import parse_json_object

            try:
                validate(parse_json_object(text), schema)
            except Exception:  # noqa: BLE001 - never echo upstream model content
                raise ValueError("Ollama output failed the task schema") from None
            return text
        key = await asyncio.to_thread(self.credentials.get, provider)
        body: dict[str, Any]
        if provider == "openai":
            path = "/responses"
            body = {
                "model": binding.model,
                "instructions": instruction,
                "input": prompt,
                "store": False,
                "max_output_tokens": binding.max_output_tokens,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "interview_result",
                        "strict": True,
                        "schema": schema,
                    }
                },
            }
            if binding.reasoning:
                body["reasoning"] = {"effort": binding.reasoning}
        elif provider == "anthropic":
            schema = _anthropic_schema(schema)
            path = "/messages"
            body = {
                "model": binding.model,
                "system": instruction,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": binding.max_output_tokens,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            }
            if binding.reasoning:
                body["output_config"]["effort"] = binding.reasoning
        elif provider == "google":
            path = "/models/" + quote(binding.model, safe="-._") + ":generateContent"
            body = {
                "systemInstruction": {"parts": [{"text": instruction}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": binding.max_output_tokens,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                },
            }
            if binding.reasoning:
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": binding.reasoning.upper()}
        else:
            raise ValueError("Cloud adapter does not accept local inference")
        data, meta = await self._request(provider, "POST", path, key, body=body)
        if provider == "openai":
            if data.get("status") == "incomplete":
                raise ProviderError(
                    "Model output was truncated. Retry saved answers with a larger output allowance.",
                    code="OUTPUT_LIMIT",
                    dispatch="sent",
                    finish_reason="max_tokens",
                )
            text = "".join(
                part.get("text", "")
                for item in data.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            usage = data.get("usage", {})
        elif provider == "anthropic":
            if data.get("stop_reason") == "max_tokens":
                raise ProviderError(
                    "Model output was truncated. Retry saved answers with a larger output allowance.",
                    code="OUTPUT_LIMIT",
                    dispatch="sent",
                    finish_reason="max_tokens",
                )
            text = "".join(p.get("text", "") for p in data.get("content", []) if p.get("type") == "text")
            usage = data.get("usage", {})
        else:
            candidates = data.get("candidates", [])
            if not candidates or candidates[0].get("finishReason") not in {None, "STOP"}:
                reason = candidates[0].get("finishReason") if candidates else "NO_CANDIDATE"
                safe_reason = (
                    reason
                    if reason
                    in {
                        "MAX_TOKENS",
                        "SAFETY",
                        "RECITATION",
                        "LANGUAGE",
                        "OTHER",
                        "BLOCKLIST",
                        "PROHIBITED_CONTENT",
                        "SPII",
                        "MALFORMED_RESPONSE",
                        "NO_CANDIDATE",
                    }
                    else "OTHER"
                )
                raise ProviderError(
                    "Provider did not return a complete usable answer",
                    code="OUTPUT_LIMIT" if safe_reason == "MAX_TOKENS" else "PROVIDER_REFUSAL",
                    dispatch="sent",
                    finish_reason=safe_reason,
                )
            text = "".join(
                p.get("text", "")
                for p in candidates[0].get("content", {}).get("parts", [])
                if not p.get("thought")
            )
            counts = data.get("usageMetadata", {})
            usage = {
                "input_tokens": counts.get("promptTokenCount", 0),
                "output_tokens": counts.get("candidatesTokenCount", 0) + counts.get("thoughtsTokenCount", 0),
            }
        if isinstance(text, str) and key in text:
            raise ProviderError("Provider returned unsafe output. Reconnect and try a different model.")
        if not text or len(text) > 100_000:
            raise ProviderError("Provider returned no usable bounded text")
        usage = {
            k: v
            for k, v in usage.items()
            if k in {"input_tokens", "output_tokens"} and type(v) is int and v >= 0
        }
        returned = data.get("model", data.get("modelVersion", binding.model))
        self.last_call = {
            "provider": provider,
            "requested_model": binding.model,
            "returned_model": returned
            if isinstance(returned, str)
            and re.fullmatch(r"[\w./:-]{1,150}", returned)
            and key not in returned
            else binding.model,
            "usage": usage,
            "estimated_usd": estimated_cost(provider, binding.model, usage),
            **meta,
        }
        return text


def _anthropic_schema(value: Any) -> Any:
    """Claude's constrained decoder omits bounds; local validators still enforce them."""
    if isinstance(value, list):
        return [_anthropic_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    omitted = {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}
    result = {key: _anthropic_schema(item) for key, item in value.items() if key not in omitted}
    constraints = [f"{key}: {value[key]}" for key in omitted if key in value]
    if constraints:
        result["description"] = (result.get("description", "") + " " + "; ".join(constraints)).strip()
    return result
