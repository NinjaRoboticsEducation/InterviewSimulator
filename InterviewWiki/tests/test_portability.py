from __future__ import annotations

import re
from pathlib import Path

from interviewwiki.config import Config


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_and_agent_files_have_no_machine_specific_paths() -> None:
    roots = [
        ROOT / "src",
        ROOT / "schemas",
        ROOT / "templates",
        ROOT / ".agents",
        ROOT / ".claude",
        ROOT / ".cursor",
        ROOT / "prompts",
    ]
    files = [ROOT / "interviewwiki.yaml", ROOT / "pyproject.toml", ROOT / "README.md"]
    for base in roots:
        files.extend(
            path
            for path in base.rglob("*")
            if path.is_file() and path.suffix in {".css", ".html", ".js", ".json", ".md", ".py", ".toml", ".yaml", ".yml"}
        )
    forbidden = re.compile(r"/(?:Users|Volumes)/|[A-Za-z]:\\\\Users\\\\")
    violations = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if forbidden.search(text):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []


def test_runtime_data_locations_are_separate_and_derived_state_is_ignored() -> None:
    config = Config.load(ROOT)
    data_roots = {
        config.job_descriptions,
        config.personal_wiki,
        config.output,
        config.runtime,
    }

    assert len(data_roots) == 4
    assert all(path.is_relative_to(config.root) for path in data_roots)
    assert not config.runtime.is_relative_to(config.personal_wiki)
    assert not config.personal_wiki.is_relative_to(config.runtime)
    assert ".interviewwiki/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_declared_clean_template_contains_no_user_or_generated_data() -> None:
    config = Config.load(ROOT)
    if not bool((config.settings.get("distribution") or {}).get("clean_template", False)):
        return

    material_files = []
    for directory in (config.job_descriptions, config.output):
        material_files.extend(
            path.relative_to(ROOT).as_posix()
            for path in directory.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        )
    allowed_blank_wiki = {
        "analyses/index.md", "concepts/index.md", "entities/index.md", "references/index.md",
        "index.md", "log.md", "overview.md",
    }
    personal_material = []
    raw_root = config.personal_wiki / "raw"
    if raw_root.exists():
        personal_material.extend(
            path.relative_to(ROOT).as_posix()
            for path in raw_root.rglob("*")
            if path.is_file()
            and path.name != ".gitkeep"
            and path.relative_to(raw_root).as_posix() != "_catalog/index.yaml"
        )
    wiki_root = config.personal_wiki / "wiki"
    if wiki_root.exists():
        personal_material.extend(
            path.relative_to(ROOT).as_posix()
            for path in wiki_root.rglob("*")
            if path.is_file()
            and path.name != ".gitkeep"
            and path.relative_to(wiki_root).as_posix() not in allowed_blank_wiki
        )
    derived = [
        path.relative_to(ROOT).as_posix()
        for path in (config.runtime / "candidate-facts.json", config.runtime / "candidate-migrations")
        if path.exists()
    ]

    assert material_files == []
    assert personal_material == []
    assert derived == []
