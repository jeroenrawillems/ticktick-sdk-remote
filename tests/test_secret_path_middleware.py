"""Tests for SecretPathMiddleware (inbound auth via a secret URL path segment).

The middleware is the only thing standing between a guessed hostname and full
access to the owner's TickTick account, so these tests cover both directions:
correct prefixes must pass through with the path rewritten, and everything else
must 404 without reaching the wrapped app.
"""

from __future__ import annotations

from ticktick_sdk.server import SecretPathMiddleware

SECRET = "s3cr3t-path-value-1234"


class RecordingApp:
    """Downstream ASGI app that records the scope it was called with."""

    def __init__(self) -> None:
        self.called = False
        self.scope: dict | None = None

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        self.scope = scope


def http_scope(path: str, raw_path: bytes | None = None) -> dict:
    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    if raw_path is not None:
        scope["raw_path"] = raw_path
    return scope


class ResponseCollector:
    """Collects ASGI send() messages so the status code can be asserted."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for message in self.messages:
            if message["type"] == "http.response.start":
                return message["status"]
        return None


async def noop_receive() -> dict:  # pragma: no cover - never produces a body
    return {"type": "http.request", "body": b"", "more_body": False}


async def test_correct_prefix_passes_through_and_strips_path():
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)
    send = ResponseCollector()

    await middleware(http_scope(f"/{SECRET}/mcp"), noop_receive, send)

    assert app.called
    # The wrapped MCP app must see its normal path, not the secret one.
    assert app.scope["path"] == "/mcp"


async def test_raw_path_is_stripped_too():
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)

    await middleware(
        http_scope(f"/{SECRET}/mcp", raw_path=f"/{SECRET}/mcp".encode()),
        noop_receive,
        ResponseCollector(),
    )

    assert app.scope["raw_path"] == b"/mcp"


async def test_prefix_only_maps_to_root():
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)

    await middleware(http_scope(f"/{SECRET}"), noop_receive, ResponseCollector())

    assert app.called
    assert app.scope["path"] == "/"


async def test_bare_mcp_is_rejected():
    """The whole point: probing /mcp without the secret must not reach the app."""
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)
    send = ResponseCollector()

    await middleware(http_scope("/mcp"), noop_receive, send)

    assert not app.called
    assert send.status == 404


async def test_wrong_secret_is_rejected():
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)
    send = ResponseCollector()

    await middleware(http_scope("/not-the-secret/mcp"), noop_receive, send)

    assert not app.called
    assert send.status == 404


async def test_secret_as_later_segment_is_rejected():
    """The secret must be the FIRST segment, not merely present somewhere."""
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)
    send = ResponseCollector()

    await middleware(http_scope(f"/mcp/{SECRET}"), noop_receive, send)

    assert not app.called
    assert send.status == 404


async def test_partial_prefix_is_rejected():
    """A prefix of the secret must not be accepted as the secret."""
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)
    send = ResponseCollector()

    await middleware(http_scope(f"/{SECRET[:8]}/mcp"), noop_receive, send)

    assert not app.called
    assert send.status == 404


async def test_health_is_exempt():
    """Railway's healthcheck hits /health with no secret; a 404 would fail deploys."""
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)

    await middleware(http_scope("/health"), noop_receive, ResponseCollector())

    assert app.called
    assert app.scope["path"] == "/health"


async def test_non_http_scopes_pass_through():
    """Lifespan startup/shutdown must not be swallowed by the path check."""
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, SECRET)

    await middleware({"type": "lifespan"}, noop_receive, ResponseCollector())

    assert app.called


async def test_surrounding_slashes_in_config_are_tolerated():
    """Setting MCP_SECRET_PATH to '/foo/' should behave the same as 'foo'."""
    app = RecordingApp()
    middleware = SecretPathMiddleware(app, f"/{SECRET}/")

    await middleware(http_scope(f"/{SECRET}/mcp"), noop_receive, ResponseCollector())

    assert app.called
    assert app.scope["path"] == "/mcp"
