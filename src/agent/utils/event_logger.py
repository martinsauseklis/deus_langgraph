"""Compact per-thread JSON-lines event stream for machine-readable debugging."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOGS_DIR = os.getenv("LOGS_DIR", "/tmp/deus_logs")
_MAX_OUTPUT_CHARS = 2000

# Per-file write locks so concurrent threads don't interleave lines.
_file_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _registry_lock:
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        return _file_locks[path]


def _truncate(value: Any) -> tuple[str, bool]:
    s = str(value)
    if len(s) > _MAX_OUTPUT_CHARS:
        return s[:_MAX_OUTPUT_CHARS], True
    return s, False


def log_event(thread_id: str, node: str, event: str, **extra: Any) -> None:
    """Append one event line to LOGS_DIR/events/<thread_id>.jsonl.

    Never raises — logging failures must not crash the agent.
    """
    # Re-read env at call time so hot-reloads and late env-var setting don't
    # result in a stale None value captured at import time.
    logs_dir = os.getenv("LOGS_DIR") or _LOGS_DIR
    if not thread_id or not logs_dir:
        return
    try:
        events_dir = Path(logs_dir) / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        path = events_dir / f"{thread_id}.jsonl"

        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id,
            "node": node,
            "event": event,
            **extra,
        }
        line = json.dumps(record, default=str) + "\n"

        lock = _lock_for(str(path))
        with lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        pass


def log_tool_call(thread_id: str, tool_name: str, args: Any) -> None:
    """Log a tool invocation before execution."""
    s, truncated = _truncate(args)
    log_event(
        thread_id,
        "tool_node",
        "tool_call",
        tool=tool_name,
        input=s,
        input_truncated=truncated,
    )


def log_tool_result(thread_id: str, tool_call_id: str, tool_name: str, output: Any) -> None:
    """Log a tool result after execution."""
    s, truncated = _truncate(output)
    log_event(
        thread_id,
        "tool_node",
        "tool_result",
        tool=tool_name,
        tool_call_id=tool_call_id,
        output=s,
        output_truncated=truncated,
    )
