"""ASGI disconnect regression checks; no sockets, external services or patient data."""
import gzip
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from snomed_post_processing.gui.nicegui.transport import EarlyDisconnectGuard, guard_socketio_disconnects


class EarlyDisconnectGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_initial_http_disconnect_does_not_reach_engineio(self):
        downstream, send = AsyncMock(), AsyncMock()
        await EarlyDisconnectGuard(downstream)(
            {"type": "http"}, AsyncMock(return_value={"type": "http.disconnect"}), send,
        )
        downstream.assert_not_awaited()
        send.assert_not_awaited()

    async def test_initial_websocket_disconnect_is_ignored(self):
        downstream, send = AsyncMock(), AsyncMock()
        await EarlyDisconnectGuard(downstream)(
            {"type": "websocket"}, AsyncMock(return_value={"type": "websocket.disconnect", "code": 1006}), send,
        )
        downstream.assert_not_awaited()
        send.assert_not_awaited()

    async def test_http_body_frames_are_replayed_once_and_unchanged(self):
        first = {"type": "http.request", "body": b"first", "more_body": True}
        second = {"type": "http.request", "body": b"second", "more_body": False}
        receive, send = AsyncMock(side_effect=[first, second]), AsyncMock()

        async def downstream(scope, replay, sender):
            self.assertIs(await replay(), first)
            self.assertIs(await replay(), second)
            await sender({"type": "http.response.start", "status": 200, "headers": []})

        await EarlyDisconnectGuard(downstream)({"type": "http"}, receive, send)
        self.assertEqual(receive.await_count, 2)
        send.assert_awaited_once_with({"type": "http.response.start", "status": 200, "headers": []})

    async def test_websocket_handshake_and_later_disconnect_are_forwarded(self):
        messages = [{"type": "websocket.connect"}, {"type": "websocket.receive", "text": "hello"},
                    {"type": "websocket.disconnect", "code": 1000}]
        receive = AsyncMock(side_effect=messages)

        async def downstream(scope, replay, send):
            for expected in messages:
                self.assertIs(await replay(), expected)

        await EarlyDisconnectGuard(downstream)({"type": "websocket"}, receive, AsyncMock())
        self.assertEqual(receive.await_count, 3)

    async def test_response_header_names_are_lowercase_without_changing_values_or_body(self):
        for kind, start in (("http", "http.response.start"), ("websocket", "websocket.accept")):
            with self.subTest(kind=kind):
                original = {"type": start, "headers": [(b"Content-Encoding", b"gzip"),
                            (b"Set-Cookie", b"one"), (b"Set-Cookie", b"two")]}
                if kind == "http":
                    original["status"] = 200
                body = {"type": "http.response.body", "body": b"unchanged"}
                send = AsyncMock()

                async def downstream(scope, replay, sender):
                    await replay()
                    await sender(original)
                    if kind == "http":
                        await sender(body)

                await EarlyDisconnectGuard(downstream)(
                    {"type": kind}, AsyncMock(return_value={"type": "http.request" if kind == "http" else "websocket.connect"}), send,
                )
                self.assertEqual(send.await_args_list[0].args[0]["headers"],
                                 [(b"content-encoding", b"gzip"), (b"set-cookie", b"one"), (b"set-cookie", b"two")])
                self.assertEqual(original["headers"][0][0], b"Content-Encoding")
                if kind == "http":
                    self.assertIs(send.await_args_list[1].args[0], body)

    async def test_lifespan_is_passed_through_without_reading(self):
        downstream, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
        scope = {"type": "lifespan"}
        await EarlyDisconnectGuard(downstream)(scope, receive, send)
        downstream.assert_awaited_once_with(scope, receive, send)
        receive.assert_not_awaited()

    async def test_unrelated_errors_are_not_suppressed(self):
        downstream = AsyncMock(side_effect=KeyError("REQUEST_METHOD"))
        with self.assertRaises(KeyError):
            await EarlyDisconnectGuard(downstream)(
                {"type": "http"}, AsyncMock(return_value={"type": "http.request", "body": b""}), AsyncMock(),
            )


class TransportInstallationTest(unittest.TestCase):
    def test_wraps_only_socketio_mount_and_is_idempotent(self):
        socket_app, upload_app = object(), object()
        socket_route = SimpleNamespace(path="/_nicegui_ws/", app=socket_app)
        upload_route = SimpleNamespace(path="/_nicegui/client/upload", app=upload_app)
        app = SimpleNamespace(routes=[upload_route, socket_route])
        guard_socketio_disconnects(app)
        wrapper = socket_route.app
        self.assertIsInstance(wrapper, EarlyDisconnectGuard)
        self.assertIs(wrapper.app, socket_app)
        self.assertIs(upload_route.app, upload_app)
        guard_socketio_disconnects(app)
        self.assertIs(socket_route.app, wrapper)

    def test_missing_mount_fails_explicitly(self):
        with self.assertRaisesRegex(RuntimeError, "Socket.IO mount"):
            guard_socketio_disconnects(SimpleNamespace(routes=[]))


@unittest.skipUnless(importlib.util.find_spec("engineio"), "optional NiceGUI transport dependencies not installed")
class InstalledEngineIoRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def test_starlette_does_not_double_compress_engineio_response(self):
        from starlette.middleware.gzip import GZipMiddleware
        payload = b'42["update",{"text":"' + b'x' * 2048 + b'"}]'
        compressed = gzip.compress(payload)

        async def adapter(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"Content-Type", b"text/plain"), (b"Content-Encoding", b"gzip")]})
            await send({"type": "http.response.body", "body": compressed})

        app = GZipMiddleware(EarlyDisconnectGuard(adapter), minimum_size=1)
        send = AsyncMock()
        await app({"type": "http", "headers": [(b"accept-encoding", b"gzip")]},
                  AsyncMock(return_value={"type": "http.request", "body": b""}), send)
        messages = [call.args[0] for call in send.await_args_list]
        self.assertEqual([value for name, value in messages[0]["headers"] if name == b"content-encoding"], [b"gzip"])
        self.assertEqual(messages[1]["body"], compressed)
        self.assertEqual(gzip.decompress(messages[1]["body"]), payload)

    async def test_actual_adapter_never_receives_empty_disconnect_environment(self):
        import engineio
        for kind in ("http", "websocket"):
            with self.subTest(kind=kind):
                adapter = engineio.ASGIApp(engineio.AsyncServer(async_mode="asgi"))
                scope = {"type": kind, "path": "/engine.io/", "method": "GET", "headers": [],
                         "query_string": b"EIO=4&transport=polling"}
                send = AsyncMock()
                await EarlyDisconnectGuard(adapter)(
                    scope, AsyncMock(return_value={"type": f"{kind}.disconnect"}), send,
                )
                send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
