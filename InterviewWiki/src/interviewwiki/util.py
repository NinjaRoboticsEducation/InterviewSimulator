from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .errors import InterviewWikiError


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise InterviewWikiError("A company, role, or opportunity name must contain letters or numbers")
    return slug[:80].rstrip("-")


def parse_ref(value: str) -> tuple[str, str]:
    parts = Path(value).parts
    if len(parts) != 2 or any(not SLUG_RE.fullmatch(part) for part in parts):
        raise InterviewWikiError("Opportunity must be '<company-slug>/<opportunity-slug>'")
    return parts[0], parts[1]


def ensure_within(path: Path, root: Path, *, must_exist: bool = False) -> Path:
    root = root.resolve()
    candidate = path.resolve(strict=must_exist)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InterviewWikiError(f"Path escapes the project boundary: {path}") from exc
    return candidate


def project_path(root: Path, value: str) -> Path:
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise InterviewWikiError(f"Configured paths must be project-relative: {value}")
    return ensure_within(root / raw, root)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(serialized)


def sha256_paths(paths: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(sha256_file(path).encode("ascii"))
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InterviewWikiError(f"Could not read JSON {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_text(path: Path, text: str) -> None:
    """Atomically replace a UTF-8 text file in its destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def reject_symlink_path(path: Path, root: Path) -> None:
    """Reject a file whose path or any existing parent below root is a symlink."""
    root = root.resolve()
    current = path
    while True:
        if current.is_symlink():
            raise InterviewWikiError(f"Symlinks are not accepted as evidence: {path}")
        if current == root:
            break
        if root not in current.parents:
            raise InterviewWikiError(f"Path escapes the project boundary: {path}")
        current = current.parent


@contextmanager
def operation_lock(lock_path: Path) -> Iterator[None]:
    """Use a small, opportunity-scoped exclusive lock for mutating operations."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InterviewWikiError(f"Another InterviewWiki operation is active: {lock_path.name}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()} created={utc_now()}\n".encode("utf-8"))
        os.close(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        lock_path.unlink(missing_ok=True)


def relative_string(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
