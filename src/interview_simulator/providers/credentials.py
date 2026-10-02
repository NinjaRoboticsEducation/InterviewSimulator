from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
import uuid
from functools import wraps
from pathlib import Path
from threading import RLock

from filelock import FileLock

from ..files import private_directory, reject_links
from .base import ProviderError


def save_private_json(path: Path, value: dict) -> None:
    private_directory(path.parent)
    reject_links(path)
    descriptor, name = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def synchronized(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return function(self, *args, **kwargs)

    return guarded


class Credentials:
    """No secret fields are serialized. OS vault is opt-in and fails closed."""

    def __init__(self, root: Path):
        self._lock = RLock()
        self._keys: dict[str, str] = {}
        self._disconnected: set[str] = set()
        self.path = root / "credential-profiles.json"
        reject_links(self.path)
        device = hashlib.sha256(f"{platform.node()}:{uuid.getnode()}:{root.resolve()}".encode()).hexdigest()
        private_directory(root)
        lock_path = root / "credential-profiles.lock"
        reject_links(lock_path)
        with FileLock(lock_path, timeout=10):
            value = json.loads(self.path.read_text()) if self.path.exists() else {}
            if value.get("device") != device:
                value = {"device": device, "installation": uuid.uuid4().hex, "remembered": []}
                save_private_json(self.path, value)
            self.metadata = value

    def __repr__(self) -> str:
        return "Credentials(<server-only>)"

    def _vault(self):
        try:
            import keyring

            backend = keyring.get_keyring()
            if backend.__class__.__module__ == "keyring.backends.chainer":
                choices = getattr(backend, "backends", [])
            else:
                choices = [backend]
            for candidate in choices:
                module = candidate.__class__.__module__
                if (
                    module
                    in {
                        "keyring.backends.macOS",
                        "keyring.backends.Windows",
                        "keyring.backends.SecretService",
                        "keyring.backends.kwallet",
                    }
                    and candidate.priority > 0
                ):
                    return candidate
        except Exception:  # noqa: BLE001 - never leak upstream credentials or vault diagnostics
            return self._unavailable_vault()
        raise ProviderError("OS credential vault unavailable or locked. Use a session-only key.")

    @staticmethod
    def _unavailable_vault():
        raise ProviderError("OS credential vault unavailable or locked. Use a session-only key.")

    def _service(self) -> str:
        return "InterviewSimulator:" + self.metadata["installation"]

    @synchronized
    def set(self, provider: str, key: str, remember: bool = False) -> None:
        if provider not in {"google", "openai", "anthropic"} and not re.fullmatch(
            r"ollama-[a-f0-9]{32}", provider
        ):
            raise ValueError("Choose a cloud provider")
        if not 8 <= len(key) <= 512 or any(c.isspace() for c in key):
            raise ValueError("Enter a valid provider key without spaces")
        if remember:
            try:
                self._vault().set_password(self._service(), provider, key)
            except Exception:  # noqa: BLE001 - never leak upstream credentials or vault diagnostics
                raise ProviderError(
                    "Could not store the key in the OS vault. Use session-only storage."
                ) from None
            if provider not in self.metadata["remembered"]:
                self.metadata["remembered"].append(provider)
            save_private_json(self.path, self.metadata)
        self._keys[provider] = key
        self._disconnected.discard(provider)

    @synchronized
    def get(self, provider: str) -> str:
        if provider in self._disconnected:
            raise ProviderError("Provider disconnected. Reconnect explicitly before continuing.")
        if provider in self._keys:
            return self._keys[provider]
        if provider in self.metadata["remembered"]:
            try:
                key = self._vault().get_password(self._service(), provider)
                if key:
                    self._keys[provider] = key
                    return key
            except Exception:  # noqa: BLE001 - never leak upstream credentials or vault diagnostics
                raise ProviderError("Unlock the OS vault or reconnect this provider.") from None
        raise ProviderError("Reconnect the selected provider before continuing saved work.")

    @synchronized
    def disconnect(self, provider: str, forget: bool = False) -> None:
        if forget and provider in self.metadata["remembered"]:
            try:
                self._vault().delete_password(self._service(), provider)
            except Exception:  # noqa: BLE001 - never leak upstream credentials or vault diagnostics
                raise ProviderError(
                    "Could not forget the saved key. Unlock the OS vault and retry."
                ) from None
            self.metadata["remembered"].remove(provider)
            save_private_json(self.path, self.metadata)
        self._keys.pop(provider, None)
        self._disconnected.add(provider)

    @synchronized
    def reconnect(self, provider: str) -> str:
        self._disconnected.discard(provider)
        return self.get(provider)

    @synchronized
    def status(self) -> dict:
        return {
            p: {"connected": p in self._keys, "remembered": p in self.metadata["remembered"]}
            for p in ("google", "openai", "anthropic")
        }

    @synchronized
    def clear_memory(self) -> None:
        self._keys.clear()
