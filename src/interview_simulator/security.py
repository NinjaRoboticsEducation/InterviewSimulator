"""Browser request boundary for a single-user, loopback-only ASGI app."""

from __future__ import annotations

import asyncio
import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

REQUEST_TOKEN = secrets.token_urlsafe(32)


class LocalRequestMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        expected = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
        is_api = scope["path"].startswith("/api/")
        if (
            headers.get("sec-fetch-site") == "cross-site"
            or (origin is not None and origin != expected)
            or (is_api and not secrets.compare_digest(headers.get("x-interview-token", ""), REQUEST_TOKEN))
        ):
            await JSONResponse({"detail": "Open the simulator locally and reload the page."}, 403)(
                scope, receive, send
            )
            return

        # Bound the body before FastAPI's multipart parser can spool it to disk.
        maximum = 20_100_000 if scope["path"].startswith("/api/transcribe/") else 100_000
        try:
            declared = int(headers.get("content-length", "0"))
        except ValueError:
            declared = -1
        if declared < 0 or declared > maximum:
            await JSONResponse({"detail": "Request body is too large or invalid."}, 413)(scope, receive, send)
            return
        body = bytearray()
        try:
            async with asyncio.timeout(30):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > maximum:
                        await JSONResponse({"detail": "Request body is too large."}, 413)(
                            scope, receive, send
                        )
                        return
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "Request upload timed out."}, 408)(scope, receive, send)
            return
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                        ),
                    ]
                )
            await send(message)

        await self.app(scope, replay, secured_send)
