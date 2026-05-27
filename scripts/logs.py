#!/usr/bin/env python3
"""
Fetch and display the event log for a LangGraph thread.

Usage:
  python scripts/logs.py <thread_id>           # full event log
  python scripts/logs.py <thread_id> --errors  # errors only
  python scripts/logs.py --recent              # last 10 threads
  python scripts/logs.py --recent --errors     # recent threads that had errors
  python scripts/logs.py --recent --limit 20   # show more
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

LOGS_DIR = os.getenv("LOGS_DIR", "/tmp/deus_logs")


def get_events(thread_id: str) -> list[dict]:
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


def _fmt(ev: dict) -> str:
    ts = ev.get("ts", "?")
    node = ev.get("node", "?")
    event = ev.get("event", "?")

    if event == "tool_call":
        tool = ev.get("tool", "?")
        inp = ev.get("input", "")
        suffix = " [truncated]" if ev.get("input_truncated") else ""
        return f"  {ts} [{node}] TOOL_CALL {tool}: {inp}{suffix}"

    if event == "tool_result":
        tool = ev.get("tool", "?")
        out = ev.get("output", "")
        suffix = " [truncated]" if ev.get("output_truncated") else ""
        return f"  {ts} [{node}] TOOL_RESULT {tool}: {out}{suffix}"

    if event in ("error", "exit_with_error"):
        msg = ev.get("message", ev.get("error", ""))
        return f"!!! {ts} [{node}] ERROR: {msg}"

    if event in ("enter", "exit"):
        extra = {
            k: v
            for k, v in ev.items()
            if k not in ("ts", "thread_id", "node", "event")
        }
        tail = f"  {extra}" if extra else ""
        return f"  {ts} [{node}] {event.upper()}{tail}"

    extra = {k: v for k, v in ev.items() if k not in ("ts", "thread_id", "node", "event")}
    return f"  {ts} [{node}] {event}" + (f"  {extra}" if extra else "")


def show_thread(thread_id: str, errors_only: bool = False) -> None:
    events = get_events(thread_id)
    if not events:
        print(f"No events found for thread: {thread_id}")
        return

    to_show = [e for e in events if e.get("event") in ("error", "exit_with_error")] if errors_only else events

    print(f"\n=== {thread_id}  ({len(events)} events) ===")
    for ev in to_show:
        print(_fmt(ev))

    errors = [e for e in events if e.get("event") in ("error", "exit_with_error")]
    nodes = list(dict.fromkeys(e["node"] for e in events if e.get("event") == "enter"))
    tool_calls = [e for e in events if e.get("event") == "tool_call"]

    print(f"\n  Flow:       {' → '.join(nodes)}")
    print(f"  Tool calls: {len(tool_calls)}")
    print(f"  Errors:     {len(errors)}")


def show_recent(limit: int, errors_only: bool = False) -> None:
    events_dir = Path(LOGS_DIR) / "events"
    if not events_dir.exists():
        print("No events directory found. Is LOGS_DIR set and has the agent run?")
        return

    files = sorted(events_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if errors_only:
        filtered = [f for f in files if any(
            e.get("event") in ("error", "exit_with_error") for e in get_events(f.stem)
        )]
        files = filtered

    files = files[:limit]
    if not files:
        print("No matching threads found.")
        return

    print(f"\n{'':3} {'THREAD ID':<40} {'LAST SEEN':<22} STATUS")
    print("-" * 75)
    for f in files:
        tid = f.stem
        ts = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        evs = get_events(tid)
        has_error = any(e.get("event") in ("error", "exit_with_error") for e in evs)
        marker = "!!!" if has_error else "   "
        status = "ERROR" if has_error else "ok"
        print(f"{marker} {tid:<40} {ts:<22} {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph thread event log viewer")
    parser.add_argument("thread_id", nargs="?", help="Thread ID to inspect")
    parser.add_argument("--errors", action="store_true", help="Show only error events")
    parser.add_argument("--recent", action="store_true", help="List recent thread IDs")
    parser.add_argument("--limit", type=int, default=10, help="Max threads to list (default 10)")
    args = parser.parse_args()

    if args.recent:
        show_recent(args.limit, errors_only=args.errors)
        return

    if not args.thread_id:
        parser.print_help()
        sys.exit(1)

    show_thread(args.thread_id, errors_only=args.errors)


if __name__ == "__main__":
    main()
