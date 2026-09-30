from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .config import Config
from .errors import InterviewWikiError


def schema_path(config: Config, name: str) -> Path:
    path = config.root / "schemas" / f"{name}.schema.json"
    if not path.is_file():
        raise InterviewWikiError(f"Missing schema: {path}")
    return path


def validate_data(config: Config, name: str, data: Any) -> list[str]:
    schema = json.loads(schema_path(config, name).read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(data),
        key=lambda item: [str(part) for part in item.path],
    )
    output = []
    for error in errors:
        location = ".".join(str(part) for part in error.path)
        output.append(f"{location}: {error.message}" if location else error.message)
    return output
