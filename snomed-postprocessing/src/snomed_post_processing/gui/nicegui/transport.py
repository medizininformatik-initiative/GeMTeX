"""Narrow ASGI compliance guard for the installed Engine.IO adapter.

An initial disconnect becomes an empty WSGI environment and then a KeyError.
Mixed-case response headers also prevent Starlette detecting Engine.IO's gzip,
causing double compression. Handle only these protocol boundaries on the
Socket.IO mount: no invented requests, body changes or hidden downstream errors.
"""
from __future__ import annotations


class EarlyDisconnectGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        first = await receive()
        if first.get("type") in ("http.disconnect", "websocket.disconnect"):
            return

        async def replay_receive():
            nonlocal first
            if first is not None:
                message, first = first, None
                return message
            return await receive()

        async def forward_send(message):
            if message["type"] in ("http.response.start", "websocket.accept") and "headers" in message:
                # ASGI requires lowercase names. Preserve values, order and repeats.
                message = {**message, "headers": [(name.lower(), value) for name, value in message["headers"]]}
            return await send(message)

        return await self.app(scope, replay_receive, forward_send)


def guard_socketio_disconnects(app) -> None:
    """Install disconnect/header protection once, before starting the server."""
    for route in app.routes:
        if getattr(route, "path", "").rstrip("/") == "/_nicegui_ws":
            if not isinstance(route.app, EarlyDisconnectGuard):
                route.app = EarlyDisconnectGuard(route.app)
            return
    raise RuntimeError("Cannot locate NiceGUI's Socket.IO mount for the early-disconnect guard.")
