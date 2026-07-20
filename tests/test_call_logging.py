"""Tests for tool-call logging.

The point of this logging is attribution: when a phone app and a scheduled
routine share one deployment, the logs must say which of them made a call. These
tests pin down that the wrapping actually takes effect (it assigns to an
attribute on an SDK model, which could silently fail), that the client label is
read from the MCP handshake, and that a broken label can never break a tool.
"""

from __future__ import annotations

import logging

import pytest

from ticktick_sdk.server import _client_label, _install_call_logging, mcp


class FakeClientInfo:
    def __init__(self, name, version=None):
        self.name = name
        self.version = version


class FakeParams:
    def __init__(self, client_info):
        self.clientInfo = client_info


class FakeSession:
    def __init__(self, client_params):
        self.client_params = client_params


class FakeCtx:
    def __init__(self, session):
        self.session = session


def ctx_for(name, version=None):
    return FakeCtx(FakeSession(FakeParams(FakeClientInfo(name, version))))


# ---- _client_label ----

def test_label_uses_name_and_version():
    assert _client_label(ctx_for("TrackyTime", "1.0")) == "TrackyTime/1.0"


def test_label_without_version():
    assert _client_label(ctx_for("TrackyTime")) == "TrackyTime"


def test_label_distinguishes_two_clients():
    """The whole reason this exists: two callers must not look the same."""
    app = _client_label(ctx_for("TrackyTime", "1.0"))
    other = _client_label(ctx_for("claude-ai", "0.1.0"))
    assert app != other


@pytest.mark.parametrize("bad_ctx", [None, object(), FakeCtx(None), FakeCtx(FakeSession(None))])
def test_label_never_raises_on_odd_input(bad_ctx):
    """A log line must never be the reason a tool call fails."""
    assert _client_label(bad_ctx) == "unknown"


# ---- wrapping ----

def test_wrapping_actually_applies_and_is_idempotent():
    """Guards against the assignment silently not sticking on an SDK model."""
    _install_call_logging()
    tools = mcp._tool_manager.list_tools()
    assert tools, "expected the server to have registered tools"
    assert all(getattr(t.fn, "_ticktick_call_logged", False) for t in tools)

    # Running again must not double-wrap.
    before = [t.fn for t in mcp._tool_manager.list_tools()]
    _install_call_logging()
    after = [t.fn for t in mcp._tool_manager.list_tools()]
    assert before == after


async def test_call_is_logged_with_tool_name_and_client(caplog):
    _install_call_logging()
    tool = mcp._tool_manager.list_tools()[0]

    with caplog.at_level(logging.INFO, logger="ticktick_sdk.server"):
        try:
            await tool.fn(ctx=ctx_for("TrackyTime", "1.0"))
        except Exception:
            # The tool itself will fail without real arguments or a live client;
            # what matters is that the call was logged on the way in.
            pass

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert f"tool call: {tool.name}" in logged
    assert "client=TrackyTime/1.0" in logged


async def test_failures_log_the_type_but_not_the_message(caplog):
    """Error messages must not reach the logs: they quote the payload back.

    A pydantic validation error includes input_value={'tasks': [{'title': ...}]},
    so logging str(exception) would put real task titles into a hosting
    dashboard. Only the exception class name is safe.
    """
    secret = "Dentist appointment 14:00"

    async def boom(**kwargs):
        raise ValueError(f"validation failed: input_value={{'title': '{secret}'}}")

    class FakeTool:
        name = "ticktick_fake"
        fn = staticmethod(boom)

    tool = FakeTool()
    wrapped = None

    # Wrap by hand with the same logic the installer uses.
    from ticktick_sdk.server import _install_call_logging  # noqa: F401
    import ticktick_sdk.server as srv

    original = srv.mcp._tool_manager.list_tools
    srv.mcp._tool_manager.list_tools = lambda: [tool]
    try:
        srv._install_call_logging()
        wrapped = tool.fn
    finally:
        srv.mcp._tool_manager.list_tools = original

    with caplog.at_level(logging.INFO, logger="ticktick_sdk.server"):
        with pytest.raises(ValueError):
            await wrapped(ctx=ctx_for("TrackyTime", "1.0"))

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "ValueError" in logged, "the exception type should be recorded"
    assert secret not in logged, "personal data leaked into the logs"
    assert "input_value" not in logged
