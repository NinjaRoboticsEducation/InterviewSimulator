from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import InterviewWikiError


@dataclass(frozen=True)
class Document:
    metadata: dict[str, Any]
    body: str


def parse_text(text: str, source: str = "<text>") -> Document:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise InterviewWikiError(f"{source}: missing YAML frontmatter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise InterviewWikiError(f"{source}: missing closing frontmatter delimiter")
    try:
        metadata = yaml.safe_load(normalized[4:end]) or {}
    except yaml.YAMLError as exc:
        raise InterviewWikiError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(metadata, dict):
        raise InterviewWikiError(f"{source}: frontmatter must be a mapping")
    return Document(metadata=metadata, body=normalized[end + 5 :])


def parse_file(path: Path) -> Document:
    return parse_text(path.read_text(encoding="utf-8"), str(path))
