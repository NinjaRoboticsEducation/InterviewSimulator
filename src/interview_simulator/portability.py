"""Offline, stopped-server export, restore, and selective run removal."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from filelock import FileLock

from .adk_runtime import InterviewFlow
from .config import Settings
from .files import private_directory, reject_links
from .storage import Store
from .wiki import WikiAdapter


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _lease(settings: Settings) -> FileLock:
    private_directory(settings.state_root)
    lock = settings.state_root / "server.lock"
    reject_links(lock)
    return FileLock(lock, timeout=0)


def export_state(settings: Settings, destination: Path) -> Path:
    """Back up private simulator state; a separately copied wiki supplies source packages."""
    reject_links(destination)
    if destination.exists():
        raise FileExistsError(destination)
    with _lease(settings):
        store = Store(settings.state_root / "question-bank.sqlite")
        wiki = WikiAdapter(settings.wiki_root)
        with tempfile.TemporaryDirectory(prefix="sim-export-") as scratch:
            stage = Path(scratch)
            payloads: dict[str, bytes] = {}
            for name in ("question-bank.sqlite", "adk-sessions.sqlite"):
                source = settings.state_root / name
                if not source.is_file():
                    if name == "question-bank.sqlite":
                        raise ValueError("No interview state to back up")
                    continue
                reject_links(source)
                copy = stage / name
                with sqlite3.connect(source) as db, sqlite3.connect(copy) as target:
                    db.backup(target)
                payloads[f"state/{name}"] = copy.read_bytes()
            with store.connect() as db:
                runs = db.execute("SELECT run_id, opportunity FROM runs ORDER BY run_id").fetchall()
            for row in runs:
                folder = wiki.simulation_dir(row["opportunity"], row["run_id"])
                if not folder.is_dir():
                    raise ValueError(f"Missing simulation folder for {row['run_id']}")
                for file in folder.rglob("*"):
                    reject_links(file)
                    if file.is_file():
                        relative = file.relative_to(folder)
                        if len(relative.parts) != 1:
                            raise ValueError("Unexpected nested simulation artifact")
                        payloads[f"simulations/{row['opportunity']}/{row['run_id']}/{file.name}"] = (
                            file.read_bytes()
                        )
            manifest = {
                "format": 1,
                "files": {name: _hash(data) for name, data in payloads.items()},
                "runs": [dict(row) for row in runs],
            }
            private_directory(destination.parent)
            temp = destination.with_name(destination.name + ".partial")
            reject_links(temp)
            if temp.exists():
                raise FileExistsError(temp)
            try:
                with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, data in payloads.items():
                        archive.writestr(name, data)
                    archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True).encode())
                os.replace(temp, destination)
                if os.name != "nt":
                    destination.chmod(0o600)
            finally:
                temp.unlink(missing_ok=True)
    return destination


def import_state(settings: Settings, archive_path: Path) -> None:
    reject_links(archive_path)
    with _lease(settings):
        db_target = settings.state_root / "question-bank.sqlite"
        if db_target.exists():
            raise ValueError("Restore requires an empty simulator state directory")
        wiki = WikiAdapter(settings.wiki_root)
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.namelist()
            if len(entries) != len(set(entries)) or "manifest.json" not in entries or len(entries) > 10000:
                raise ValueError("Invalid or duplicate archive entries")
            manifest = json.loads(archive.read("manifest.json"))
            expected = manifest.get("files")
            if (
                manifest.get("format") != 1
                or not isinstance(expected, dict)
                or set(entries) != set(expected) | {"manifest.json"}
            ):
                raise ValueError("Archive manifest does not match its contents")
            total = 0
            for name in expected:
                parts = Path(name).parts
                if (
                    name.startswith("/")
                    or ".." in parts
                    or "\\" in name
                    or (parts[:1] != ("state",) and parts[:1] != ("simulations",))
                    or (
                        parts[:1] == ("state",)
                        and name not in {"state/question-bank.sqlite", "state/adk-sessions.sqlite"}
                    )
                    or (parts[:1] == ("simulations",) and len(parts) != 5)
                ):
                    raise ValueError("Unsafe archive path")
                info = archive.getinfo(name)
                total += info.file_size
                if info.file_size > 1_000_000_000 or total > 5_000_000_000:
                    raise ValueError("Archive is too large")
            if "state/question-bank.sqlite" not in expected:
                raise ValueError("Missing question-bank database")
            with tempfile.TemporaryDirectory(prefix="sim-restore-") as scratch:
                stage = Path(scratch)
                for name, digest in expected.items():
                    data = archive.read(name)
                    if _hash(data) != digest:
                        raise ValueError(f"Archive checksum failed: {name}")
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                staged_db = stage / "state/question-bank.sqlite"
                with sqlite3.connect(staged_db) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Restored database failed integrity check")
                    rows = db.execute("SELECT run_id, opportunity FROM runs").fetchall()
                expected_runs = {(r["run_id"], r["opportunity"]) for r in manifest["runs"]}
                if set(rows) != expected_runs:
                    raise ValueError("Archive run inventory disagrees with database")
                destinations = []
                for run_id, reference in rows:
                    folder = wiki.simulation_dir(reference, run_id)
                    if folder.exists():
                        raise ValueError(f"Simulation already exists: {run_id}")
                    parts = reference.split("/")
                    base = f"simulations/{parts[0]}/{parts[1]}/{run_id}/"
                    if not any(name.startswith(base) for name in expected):
                        raise ValueError(f"Missing simulation artifacts for {run_id}")
                    destinations.append((stage / base, folder))
                for source, target in destinations:
                    private_directory(target.parent)
                    shutil.copytree(source, target)
                    if os.name != "nt":
                        for file in target.iterdir():
                            file.chmod(0o600)
                for name in ("question-bank.sqlite", "adk-sessions.sqlite"):
                    source = stage / "state" / name
                    if source.exists():
                        target = settings.state_root / name
                        reject_links(target)
                        shutil.copy2(source, target)
                        if os.name != "nt":
                            target.chmod(0o600)


def delete_run(settings: Settings, run_id: str) -> None:
    with _lease(settings):
        store = Store(settings.state_root / "question-bank.sqlite")
        run = store.get_run(run_id)
        folder = WikiAdapter(settings.wiki_root).simulation_dir(run["opportunity"], run_id)
        reject_links(folder)
        for item in folder.rglob("*") if folder.exists() else []:
            reject_links(item)
        with store.connect() as db:
            db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            db.execute(
                "DELETE FROM concept_versions WHERE version_id NOT IN (SELECT version_id FROM presentations)"
            )
            db.execute(
                "DELETE FROM question_versions WHERE version_id NOT IN (SELECT version_id FROM presentations)"
            )
            db.execute(
                "DELETE FROM question_concepts WHERE concept_id NOT IN (SELECT concept_id FROM concept_versions)"
            )

        async def remove_session():
            service = InterviewFlow(settings)._service()
            session = await service.get_session(
                app_name="interview_simulator", user_id="local", session_id=run_id
            )
            if session is not None:
                await service.delete_session(
                    app_name="interview_simulator", user_id="local", session_id=run_id
                )

        asyncio.run(remove_session())
        if folder.exists():
            shutil.rmtree(folder)


def verify_run(settings: Settings, run_id: str) -> dict[str, object]:
    store = Store(settings.state_root / "question-bank.sqlite")
    run = store.get_run(run_id)
    folder = WikiAdapter(settings.wiki_root).simulation_dir(run["opportunity"], run_id)
    pointer = folder / "simulation-manifest.json"
    reject_links(pointer)
    manifest = json.loads(pointer.read_text(encoding="utf-8"))
    if manifest.get("run_id") != run_id or not isinstance(manifest.get("files"), dict):
        raise ValueError("Invalid simulation manifest")
    for name, digest in manifest["files"].items():
        if Path(name).name != name or name.startswith("."):
            raise ValueError("Unsafe file name in manifest")
        file = folder / name
        reject_links(file)
        if _hash(file.read_bytes()) != digest:
            raise ValueError(f"Simulation artifact checksum mismatch: {name}")
    return {"run_id": run_id, "status": manifest["status"], "verified_files": len(manifest["files"])}
