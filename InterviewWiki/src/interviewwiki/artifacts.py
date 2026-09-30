from __future__ import annotations

from pathlib import Path


def iter_preparation_artifacts(output: Path):
    """Yield package-owned files; simulations own their separate subtree."""
    for item in output.rglob("*"):
        if not item.is_file() or item.name.startswith("."):
            continue
        relative = item.relative_to(output)
        if relative.parts[0] == "Simulations":
            continue
        if relative.as_posix() in {"Reports/run-manifest.json", "Reports/validation.json"}:
            continue
        yield item
