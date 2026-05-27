"""Shared fixtures and failure-log hooks for the e2e test suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from langgraph_sdk import get_sync_client

LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:2024")

# Prefer the env var; fall back to .env.development so tests find server-written logs
# even when the test process wasn't started with the same env as the server.
def _resolve_logs_dir() -> str:
    if val := os.getenv("LOGS_DIR"):
        return val
    env_file = Path(__file__).parents[2] / ".env.development"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LOGS_DIR="):
                return line.split("=", 1)[1].strip()
    return "/tmp/deus_logs"

LOGS_DIR = _resolve_logs_dir()


# ── Helpers ────────────────────────────────────────────────────────────────────


def get_thread_events(thread_id: str) -> list[dict]:
    """Read the event log for a thread. Returns [] if not found."""
    path = Path(LOGS_DIR) / "events" / f"{thread_id}.jsonl"
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def summarise_events(events: list[dict]) -> str:
    lines = []
    for ev in events[-100:]:
        ts = ev.get("ts", "?")
        node = ev.get("node", "?")
        event = ev.get("event", "?")
        if event == "tool_call":
            lines.append(f"  {ts} [{node}] TOOL_CALL {ev.get('tool')} input={ev.get('input','')[:200]}")
        elif event == "tool_result":
            lines.append(f"  {ts} [{node}] TOOL_RESULT {ev.get('tool')} output={ev.get('output','')[:200]}")
        elif event in ("error", "exit_with_error"):
            lines.append(f"!!! {ts} [{node}] ERROR: {ev.get('message', ev.get('error', ''))}")
        else:
            extra = {k: v for k, v in ev.items() if k not in ("ts", "thread_id", "node", "event")}
            lines.append(f"  {ts} [{node}] {event}" + (f" {extra}" if extra else ""))
    return "\n".join(lines)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def lg_client():
    """LangGraph sync SDK client. Tests in tier1 check reachability first."""
    return get_sync_client(url=LANGGRAPH_URL)


@pytest.fixture
def make_thread(lg_client):
    """Factory: creates a LangGraph thread and deletes it after the test."""
    created: list[str] = []

    def _make(metadata: dict | None = None) -> str:
        thread = lg_client.threads.create(metadata=metadata or {})
        tid = thread["thread_id"]
        created.append(tid)
        return tid

    yield _make

    for tid in created:
        try:
            lg_client.threads.delete(tid)
        except Exception:
            pass


# ── Auto log collection on failure ────────────────────────────────────────────
# The hook stores the test result on the item so the fixture teardown can read it.


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if call.when == "call":
        item._e2e_rep_call_failed = rep.failed


@pytest.fixture(autouse=True)
def _auto_collect_logs(request):
    """After every test, if it failed and we know a thread_id, attach event logs."""
    yield
    if not getattr(request.node, "_e2e_rep_call_failed", False):
        return

    # Look for any string fixture that looks like a UUID thread_id.
    for name, val in request.node.funcargs.items():
        if isinstance(val, str) and len(val) == 36 and val.count("-") == 4:
            events = get_thread_events(val)
            if events:
                print(f"\n\n{'='*70}")
                print(f"EVENT LOG for failed test — thread: {val}")
                print("="*70)
                print(summarise_events(events))
                print("="*70)
            break
