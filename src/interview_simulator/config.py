from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    root: Path
    wiki_root: Path
    state_root: Path
    model_url: str = "http://127.0.0.1:8081/v1"
    model_name: str = "interview-local"
    model_path: Path | None = None
    model_api_key: str = "local-only"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.model_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port is None
            or parsed.path != "/v1"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use a numeric HTTP loopback llama.cpp /v1 endpoint")

    @classmethod
    def load(cls, root: Path | None = None) -> Settings:
        project = (root or Path(__file__).resolve().parents[2]).resolve()
        wiki = project / "InterviewWiki"
        if not (wiki / "interviewwiki.yaml").is_file():
            raise FileNotFoundError(f"InterviewWiki configuration is missing: {wiki}")
        url = os.environ.get("INTERVIEW_SIMULATOR_MODEL_URL", cls.model_url)
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port is None
            or parsed.path != "/v1"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("The model endpoint must be an HTTP loopback llama.cpp /v1 URL")
        model_value = os.environ.get("INTERVIEW_SIMULATOR_GGUF")
        return cls(
            project,
            wiki,
            project / ".simulator",
            url,
            os.environ.get("INTERVIEW_SIMULATOR_MODEL_NAME", "interview-local"),
            (project / Path(model_value).expanduser()).resolve() if model_value else None,
            os.environ.get("INTERVIEW_SIMULATOR_MODEL_API_KEY", "local-only"),
        )
