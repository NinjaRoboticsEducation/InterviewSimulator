from __future__ import annotations

import os
from pathlib import Path


def reject_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f"Symbolic links are not allowed for simulator data: {item.name}")


def private_directory(path: Path) -> None:
    reject_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


def private_database(path: Path) -> None:
    private_directory(path.parent)
    reject_links(path)
    for suffix in ("-wal", "-shm", "-journal"):
        reject_links(Path(str(path) + suffix))
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)
    if os.name != "nt":
        path.chmod(0o600)
