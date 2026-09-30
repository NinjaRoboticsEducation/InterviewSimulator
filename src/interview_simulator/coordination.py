from __future__ import annotations

import asyncio
from functools import wraps


def serialized(attribute: str):
    """Serialize shared state within the supported single application process."""

    def decorate(function):
        @wraps(function)
        async def guarded(self, *args, **kwargs):
            lock = getattr(self, attribute, None)
            if lock is None:
                lock = asyncio.Lock()
                setattr(self, attribute, lock)
            async with lock:
                return await function(self, *args, **kwargs)

        return guarded

    return decorate
