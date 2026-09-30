from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError
from .util import project_path


@dataclass(frozen=True)
class Config:
    root: Path
    job_descriptions: Path
    personal_wiki: Path
    output: Path
    runtime: Path
    resume_template: Path
    settings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, start: Path | str = ".") -> "Config":
        root = find_root(Path(start))
        config_path = root / "interviewwiki.yaml"
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"Could not read {config_path}: {exc}") from exc
        if raw.get("version") != 1:
            raise ConfigurationError("interviewwiki.yaml must contain version: 1")
        paths = raw.get("paths")
        if not isinstance(paths, dict):
            raise ConfigurationError("interviewwiki.yaml paths must be a mapping")
        required = {
            "job_descriptions",
            "personal_wiki",
            "output",
            "runtime",
            "resume_template",
        }
        missing = sorted(required - set(paths))
        if missing:
            raise ConfigurationError("Missing configured path(s): " + ", ".join(missing))
        try:
            resolved = {name: project_path(root, str(paths[name])) for name in required}
        except Exception as exc:
            raise ConfigurationError(str(exc)) from exc
        return cls(
            root=root,
            job_descriptions=resolved["job_descriptions"],
            personal_wiki=resolved["personal_wiki"],
            output=resolved["output"],
            runtime=resolved["runtime"],
            resume_template=resolved["resume_template"],
            settings=raw,
        )

    def opportunity_source(self, reference: tuple[str, str]) -> Path:
        return self.job_descriptions.joinpath(*reference)

    def opportunity_output(self, reference: tuple[str, str]) -> Path:
        return self.output.joinpath(*reference)


def find_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "interviewwiki.yaml").is_file():
            return candidate
    raise ConfigurationError(f"No interviewwiki.yaml found from {start}")
