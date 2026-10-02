"""Build a clean, reviewable source directory without private or generated data."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

TOP_FILES = {"README.md", "LICENSE", "pyproject.toml", "uv.lock", ".gitignore", ".env.example"}
TOP_DIRS = {"src", "agents", "tests", "scripts", "config", ".github"}
PRIVATE = {
    ".git",
    ".venv",
    ".simulator",
    ".llmwiki",
    ".interviewwiki",
    ".adk",
    ".serena",
    "__pycache__",
    ".pytest_cache",
    "models",
    "JobDescriptions",
    "Output",
    "raw",
    "wiki",
}


def release_files(root: Path) -> list[Path]:
    candidates = [root / name for name in TOP_FILES if (root / name).is_file()]
    candidates += [file for folder in TOP_DIRS for file in (root / folder).rglob("*") if file.is_file()]
    candidates += [
        file
        for file in (root / "doc").rglob("*")
        if file.is_file() and file.suffix == ".md" and file.name != "prompt.md"
    ]
    # Required wiki code is tracked by the parent repository; nested metadata is excluded.
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z", "InterviewWiki"], cwd=root).decode().split("\0")
    )
    candidates += [root / name for name in tracked if name]
    result = []
    for file in candidates:
        relative = file.relative_to(root)
        if any(part in PRIVATE for part in relative.parts) or file.suffix in {
            ".pyc",
            ".sqlite",
            ".gguf",
            ".jsonl",
        }:
            continue
        if file.name.startswith(".env") and file.name != ".env.example":
            continue
        if any(item.is_symlink() for item in (file, *file.parents)):
            raise ValueError(f"Release cannot contain a symbolic link: {relative}")
        result.append(file)
    return sorted(set(result))


def build(root: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError("Choose a new empty destination; existing files are never overwritten")
    files = release_files(root)
    manifest = {}
    for file in files:
        relative = file.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        manifest[str(relative)] = hashlib.sha256(file.read_bytes()).hexdigest()
    # The wiki tools expect these empty input/output roots after a fresh clone.
    for relative in (
        "InterviewWiki/JobDescriptions",
        "InterviewWiki/Output",
        "InterviewWiki/PersonalWiki/raw/articles",
        "InterviewWiki/PersonalWiki/raw/notes",
        "InterviewWiki/PersonalWiki/raw/papers",
        "InterviewWiki/PersonalWiki/raw/media",
        "InterviewWiki/PersonalWiki/wiki",
    ):
        (destination / relative).mkdir(parents=True, exist_ok=True)
        (destination / relative / ".gitkeep").touch()
    (destination / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"files": len(manifest), "destination": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[1], args.destination.resolve())))
