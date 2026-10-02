from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["local", "google", "openai", "anthropic", "ollama"]
TASKS = ("questions", "evaluation", "coaching", "summary")


class ProviderError(RuntimeError):
    """An intentionally content-free error safe to display or persist."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PROVIDER_UNAVAILABLE",
        retry_after: float | None = None,
        http_status: int | None = None,
        dispatch: str = "unknown",
        finish_reason: str | None = None,
    ):
        super().__init__(message)
        self.code, self.retry_after, self.http_status = code, retry_after, http_status
        self.dispatch, self.finish_reason = dispatch, finish_reason

    def diagnostic(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "retry_after_seconds": self.retry_after,
            "http_status": self.http_status,
            "dispatch_state": self.dispatch,
            "finish_reason": self.finish_reason,
            "recovery": "switch_provider"
            if self.code
            in {
                "RATE_LIMITED",
                "TEMPORARY_UNAVAILABLE",
                "PROVIDER_UNAVAILABLE",
                "TIMEOUT",
                "AUTHENTICATION_FAILED",
                "PROVIDER_REFUSAL",
            }
            else None,
        }


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Provider = "local"
    model: str = Field(default="interview-local", min_length=1, max_length=150, pattern=r"^[\w./:-]+$")
    max_output_tokens: int = Field(default=1024, ge=256, le=8192)
    reasoning: Literal["low", "medium", "high"] | None = None
    connection: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    locality: Literal["local", "cloud"] | None = None

    @property
    def is_cloud(self) -> bool:
        return self.provider != "local" and not (self.provider == "ollama" and self.locality == "local")


class ModelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    questions: Binding = Binding(max_output_tokens=4096)
    evaluation: Binding = Binding()
    coaching: Binding = Binding(max_output_tokens=2048)
    summary: Binding = Binding(max_output_tokens=2048)
    localization: Binding | None = None
    generate_questions: bool = False
    generate_summary: bool = False
    max_calls: int = Field(default=48, ge=1, le=60)

    @property
    def cloud_providers(self) -> set[str]:
        tasks = ["evaluation", "coaching"]
        if self.generate_questions:
            tasks.append("questions")
        if self.generate_summary:
            tasks.append("summary")
        bindings = [getattr(self, task) for task in tasks]
        bindings.append(self.localization or self.questions)
        return {binding.provider for binding in bindings if binding.is_cloud}


# This is capability evidence, not the selectable model list. Discovery supplies that list.
# Unknown IDs require a synthetic schema probe before they can be selected.
KNOWN: dict[str, dict[str, dict[str, Any]]] = {
    "google": {"gemini-3.8-flash": {"structured": True, "input_rate": 0.75, "output_rate": 3.75}},
    "openai": {
        "gpt-6.1-sol": {"structured": True, "input_rate": 2.0, "output_rate": 10.0},
        "gpt-6-astra": {"structured": True},
        "gpt-6-luna": {"structured": True, "input_rate": 0.1, "output_rate": 0.5},
    },
    "anthropic": {
        "claude-sonnet-5-5": {"structured": True, "input_rate": 2.0, "output_rate": 10.0},
        "claude-opus-5-5": {"structured": True, "input_rate": 4.0, "output_rate": 20.0},
    },
}


def estimated_cost(provider: str, model: str, usage: dict[str, int]) -> float | None:
    from datetime import UTC, date, datetime

    # Never silently keep using a research price beyond its validity window.
    if datetime.now(UTC).date() > date(2026, 12, 31):
        return None
    rates = KNOWN.get(provider, {}).get(model, {})
    if "input_rate" not in rates or not {"input_tokens", "output_tokens"} <= usage.keys():
        return None
    return round(
        (
            usage.get("input_tokens", 0) * rates["input_rate"]
            + usage.get("output_tokens", 0) * rates["output_rate"]
        )
        / 1_000_000,
        6,
    )
