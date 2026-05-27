"""setup_node error-handling tests — no LLM, no LangGraph runtime.

Calls the node function directly with mocked HTTP responses to verify
that CONFIG_SERVER errors are not silently swallowed.
  make e2e-tools
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def _sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _config(thread_id: str | None = None) -> dict:
    return {
        "metadata": {
            "thread_id": thread_id or str(uuid4()),
            "config_name": "test",
            "config_author": "test",
        }
    }


def _make_mock_session(status: int, body: str = "") -> MagicMock:
    """Build a mock aiohttp ClientSession whose POST returns the given status.

    aiohttp uses:  async with session.post(...) as response:
    So session.post() must return an async context manager directly,
    NOT a coroutine.
    """
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.text = AsyncMock(return_value=body)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    # post() is called synchronously and returns the async context manager.
    mock_session.post = MagicMock(return_value=mock_response)

    return mock_session


# ── success path ───────────────────────────────────────────────────────────────


def test_setup_node_returns_success_on_200():
    """setup_node reports success when CONFIG_SERVER returns 200."""
    mock_session = _make_mock_session(200)

    with patch("agent.utils.nodes.setup_node.node.aiohttp.ClientSession", return_value=mock_session):
        from agent.utils.nodes.setup_node.node import setup_node
        result = _sync(setup_node({"messages": [], "sequence": []}, config=_config()))

    messages = result.get("messages", [])
    assert messages, "setup_node returned no messages"
    content = messages[0].content
    assert "failed" not in content.lower(), f"Unexpected failure on 200: {content}"


# ── error paths ───────────────────────────────────────────────────────────────


def test_setup_node_reports_error_on_500():
    """setup_node must NOT silently succeed when CONFIG_SERVER returns 500."""
    mock_session = _make_mock_session(500, "Internal Server Error")

    with patch("agent.utils.nodes.setup_node.node.aiohttp.ClientSession", return_value=mock_session):
        from agent.utils.nodes.setup_node.node import setup_node
        result = _sync(setup_node({"messages": [], "sequence": []}, config=_config()))

    messages = result.get("messages", [])
    assert messages, "setup_node returned no messages on 500"
    content = messages[0].content
    assert "failed" in content.lower() or "500" in content, (
        f"setup_node did not report the error on HTTP 500. Got: {content}"
    )


def test_setup_node_reports_error_on_404():
    """setup_node must report an error on HTTP 404."""
    mock_session = _make_mock_session(404, "Not Found")

    with patch("agent.utils.nodes.setup_node.node.aiohttp.ClientSession", return_value=mock_session):
        from agent.utils.nodes.setup_node.node import setup_node
        result = _sync(setup_node({"messages": [], "sequence": []}, config=_config()))

    content = result["messages"][0].content
    assert "failed" in content.lower() or "404" in content, (
        f"setup_node did not report the 404 error. Got: {content}"
    )


def test_setup_node_reports_error_on_connection_failure():
    """setup_node must not raise when CONFIG_SERVER is unreachable."""
    import aiohttp

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(
        side_effect=aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError("connection refused")
        )
    )
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.utils.nodes.setup_node.node.aiohttp.ClientSession", return_value=mock_session):
        from agent.utils.nodes.setup_node.node import setup_node
        result = _sync(setup_node({"messages": [], "sequence": []}, config=_config()))

    content = result["messages"][0].content
    assert "failed" in content.lower() or "could not reach" in content.lower(), (
        f"setup_node did not report connection failure. Got: {content}"
    )
