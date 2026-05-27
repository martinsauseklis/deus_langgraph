"""Full end-to-end flow tests — real LLM calls, real services.

Requires:
  - LangGraph dev server running
  - CONFIG_SERVER running (for create=True flows)
  - WORKSPACE_DIR set

  make e2e-flow
  make e2e  (runs everything)
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import requests

from tests.e2e.conftest import get_thread_events

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")
pytestmark = pytest.mark.e2e_flow


# ── Existing-project flow (no CONFIG_SERVER needed) ───────────────────────────


def _run_and_wait(lg_client, thread_id: str, messages: list[dict], create: bool = False) -> dict:
    return lg_client.runs.wait(
        thread_id,
        "agent",
        input={
            "create": create,
            "messages": messages,
            "tool_call_count": 0,
            "testing_tool_call_count": 0,
            "sequence": [],
        },
        metadata={"thread_id": thread_id},
    )


@pytest.fixture
def workspace_for_thread():
    """Creates a minimal Next.js-like workspace at WORKSPACE_DIR/<thread_id>."""
    created: list[Path] = []

    def _make(thread_id: str) -> Path:
        assert WORKSPACE_DIR, "WORKSPACE_DIR must be set"
        p = Path(WORKSPACE_DIR) / thread_id
        p.mkdir(parents=True, exist_ok=True)
        (p / "package.json").write_text(
            '{"name":"test","version":"0.0.1","scripts":{"build":"echo ok","dev":"echo dev"}}'
        )
        (p / "src").mkdir(exist_ok=True)
        (p / "src" / "page.tsx").write_text('export default function Home() { return <div>Hello</div>; }\n')
        created.append(p)
        return p

    yield _make

    for p in created:
        shutil.rmtree(p, ignore_errors=True)


def test_planner_routes_developer_for_code_task(lg_client, make_thread, workspace_for_thread):
    """Planner correctly routes a code-writing task to developer_node."""
    thread_id = make_thread()
    workspace_for_thread(thread_id)

    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "Add a README.md file with the title 'My App'"}],
    )

    events = get_thread_events(thread_id)
    nodes_entered = [e["node"] for e in events if e.get("event") == "enter"]

    assert "developer_node" in nodes_entered, (
        f"developer_node was not invoked. Nodes: {nodes_entered}"
    )

    readme = Path(WORKSPACE_DIR) / thread_id / "README.md"
    assert readme.exists(), "README.md was not created"


def test_planner_routes_business_analyst_for_requirements(lg_client, make_thread, workspace_for_thread):
    """Planner involves business_analyst_node for high-level requirements requests."""
    thread_id = make_thread()
    workspace_for_thread(thread_id)

    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "What features should a simple todo app have?"}],
    )

    events = get_thread_events(thread_id)
    nodes_entered = [e["node"] for e in events if e.get("event") == "enter"]
    assert "business_analyst_node" in nodes_entered, (
        f"business_analyst_node not invoked for requirements question. Nodes: {nodes_entered}"
    )


def test_no_orphaned_errors_after_normal_flow(lg_client, make_thread, workspace_for_thread):
    """A normal task flow produces no error events in the log."""
    thread_id = make_thread()
    workspace_for_thread(thread_id)

    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "Add a .gitignore that ignores node_modules"}],
    )

    events = get_thread_events(thread_id)
    errors = [e for e in events if e.get("event") in ("error", "exit_with_error")]
    assert errors == [], f"Unexpected errors in clean flow: {errors}"


# ── Create flow (needs CONFIG_SERVER) ─────────────────────────────────────────


@pytest.mark.skipif(not CONFIG_SERVER, reason="CONFIG_SERVER not set — skipping create=True tests")
def test_create_flow_calls_setup_and_indexes(lg_client, make_thread):
    """create=True flow: setup_node calls CONFIG_SERVER, then index_project runs."""
    thread_id = make_thread()

    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "Create a simple todo app"}],
        create=True,
    )

    events = get_thread_events(thread_id)
    nodes_entered = [e["node"] for e in events if e.get("event") == "enter"]

    assert "setup_node" in nodes_entered, f"setup_node not entered. Flow: {nodes_entered}"
    assert "index_project" in nodes_entered, f"index_project not entered. Flow: {nodes_entered}"

    errors = [e for e in events if e.get("event") in ("error", "exit_with_error")]
    assert errors == [], f"Errors during create flow: {errors}"


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_message_does_not_crash(lg_client, make_thread, workspace_for_thread):
    """Sending an empty/whitespace message should not throw an unhandled exception."""
    thread_id = make_thread()
    workspace_for_thread(thread_id)

    try:
        _run_and_wait(
            lg_client,
            thread_id,
            [{"role": "human", "content": "   "}],
        )
    except Exception as exc:
        events = get_thread_events(thread_id)
        pytest.fail(f"Empty message caused exception: {exc}. Events: {events}")


def test_setup_node_does_not_proceed_silently_on_config_server_error(
    lg_client, make_thread, monkeypatch
):
    """
    DOCUMENTS: setup_node currently ignores CONFIG_SERVER HTTP errors.
    The graph continues even if setup failed.
    This test will xfail until the bug is fixed.
    """
    thread_id = make_thread()

    # Deliberately break CONFIG_SERVER by pointing at a port nothing listens on.
    monkeypatch.setenv("CONFIG_SERVER", "http://localhost:1")

    with pytest.raises(Exception):
        _run_and_wait(
            lg_client,
            thread_id,
            [{"role": "human", "content": "Create a simple app"}],
            create=True,
        )

    pytest.xfail(
        "KNOWN BUG: setup_node ignores CONFIG_SERVER errors and returns success anyway. "
        "This test should pass after the bug is fixed."
    )
