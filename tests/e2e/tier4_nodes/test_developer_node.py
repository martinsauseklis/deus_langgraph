"""Developer node integration tests — real LLM calls via HTTP API.

Requires the LangGraph dev server to be running:
  langgraph dev --config langgraph_dev.json

  make e2e-nodes
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from tests.e2e.conftest import get_thread_events

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
pytestmark = pytest.mark.e2e_nodes


@pytest.fixture
def minimal_workspace():
    """Yields a factory: call it with a thread_id to create a workspace for that thread."""
    created: list[Path] = []

    def _make(thread_id: str) -> Path:
        assert WORKSPACE_DIR, "WORKSPACE_DIR must be set"
        proj = Path(WORKSPACE_DIR) / thread_id
        proj.mkdir(parents=True, exist_ok=True)
        # Minimal package.json — the build script just exits 0 to keep tests fast.
        pkg = {
            "name": "test-app",
            "version": "0.0.1",
            "scripts": {
                "build": "echo 'mock build ok'",
                "dev": "echo 'mock dev'",
            },
        }
        (proj / "package.json").write_text(json.dumps(pkg, indent=2))
        (proj / "src").mkdir(exist_ok=True)
        (proj / "src" / "index.ts").write_text("export const hello = 'world';\n")
        created.append(proj)
        return proj

    yield _make

    for p in created:
        shutil.rmtree(p, ignore_errors=True)


def _run_and_wait(lg_client, thread_id: str, messages: list[dict]) -> dict:
    return lg_client.runs.wait(
        thread_id,
        "agent",
        input={
            "create": False,
            "messages": messages,
            "tool_call_count": 0,
            "testing_tool_call_count": 0,
            "sequence": [],
        },
        metadata={"thread_id": thread_id},
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_developer_node_creates_a_file(lg_client, make_thread, minimal_workspace):
    """Developer agent successfully creates a new file in the workspace."""
    thread_id = make_thread()
    proj = minimal_workspace(thread_id)

    result = _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "Create a file called MARKER.txt in the project root containing exactly the text: BUILD_TEST_PASSED"}],
    )

    marker = proj / "MARKER.txt"
    events = get_thread_events(thread_id)
    tool_calls = [e for e in events if e.get("event") == "tool_call"]
    errors = [e for e in events if e.get("event") in ("error", "exit_with_error")]

    # Primary assertions: observable outcomes.
    assert marker.exists(), (
        f"MARKER.txt not created in workspace. "
        f"Tool calls in log: {[t.get('tool') for t in tool_calls]}. "
        f"Errors: {errors}"
    )
    assert "BUILD_TEST_PASSED" in marker.read_text(), (
        f"MARKER.txt has wrong content: {marker.read_text()!r}"
    )

    # Secondary assertions: no error events.
    assert errors == [], f"Errors in event log: {errors}"


def test_planner_resets_tool_budget_per_request(lg_client, make_thread, minimal_workspace):
    """The planner resets tool_call_count=0 for each new user request.

    Budget exhaustion is per-planning-session (one user message), not per thread lifetime.
    Pre-injecting tool_call_count=25 via update_state is wiped when the planner runs next.
    This test verifies that the planner does indeed reset the counter.
    """
    thread_id = make_thread()
    minimal_workspace(thread_id)

    # First request — let it run normally.
    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "List the files in the project root"}],
    )

    events_after_first = get_thread_events(thread_id)
    planner_exits = [
        e for e in events_after_first
        if e.get("node") == "planner_node" and e.get("event") == "exit"
    ]
    assert planner_exits, "Planner did not run on first request"

    # Second request — planner will reset tool_call_count to 0 regardless.
    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "Create a file called BUDGET_TEST.txt"}],
    )

    events_after_second = get_thread_events(thread_id)
    # After the second request, find the developer entry that came after the second planner exit.
    second_planner_exits = [
        i for i, e in enumerate(events_after_second)
        if e.get("node") == "planner_node" and e.get("event") == "exit"
    ]
    assert len(second_planner_exits) >= 2, "Expected at least 2 planner runs"

    # The developer entry after the second planner exit should have tool_call_count=0.
    second_planner_idx = second_planner_exits[1]
    post_planner = events_after_second[second_planner_idx + 1:]
    first_dev_after_planner = next(
        (e for e in post_planner if e.get("node") == "developer_node" and e.get("event") == "enter"),
        None,
    )
    assert first_dev_after_planner is not None, "Developer did not run after second planner"
    assert first_dev_after_planner.get("tool_call_count") == 0, (
        "Planner did not reset tool_call_count to 0 for the second request"
    )


def test_developer_node_no_error_events_on_simple_task(lg_client, make_thread, minimal_workspace):
    """A simple, unambiguous task produces no error events in the log."""
    thread_id = make_thread()
    minimal_workspace(thread_id)

    _run_and_wait(
        lg_client,
        thread_id,
        [{"role": "human", "content": "Add a comment '// reviewed' to the top of src/index.ts"}],
    )

    events = get_thread_events(thread_id)
    errors = [e for e in events if e.get("event") in ("error", "exit_with_error")]
    assert errors == [], f"Unexpected errors: {errors}"
