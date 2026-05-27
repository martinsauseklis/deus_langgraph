"""Infrastructure health checks — no LLM, no server invocation.

Run first to catch misconfigured environments before spending on LLM calls.
  make e2e-infra
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:2024")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
LOGS_DIR = os.getenv("LOGS_DIR")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")


def test_langgraph_server_reachable(lg_client):
    """LangGraph dev server is up and the 'agent' graph is registered."""
    assistants = lg_client.assistants.search()
    ids = [a.get("graph_id") for a in assistants]
    assert "agent" in ids, f"'agent' graph not found. Got: {ids}"


def test_langgraph_server_reachable_via_http():
    """Raw HTTP check — surfaces proxy / port issues independently of the SDK."""
    resp = requests.get(f"{LANGGRAPH_URL}/ok", timeout=5)
    assert resp.status_code == 200, f"GET /ok returned {resp.status_code}"


@pytest.mark.skipif(not os.getenv("PG_HOST"), reason="PG_HOST not set — skipping DB check")
def test_postgres_connection():
    """PostgreSQL is reachable with the configured credentials."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "mydb"),
        user=os.getenv("PG_USER", "myuser"),
        password=os.getenv("PG_PASSWORD", "mypassword"),
    )
    conn.close()


def test_workspace_dir_exists_and_writable():
    """WORKSPACE_DIR is set, exists, and is writable."""
    assert WORKSPACE_DIR, "WORKSPACE_DIR env var is not set"
    p = Path(WORKSPACE_DIR)
    assert p.exists(), f"WORKSPACE_DIR does not exist: {p}"
    assert os.access(p, os.W_OK), f"WORKSPACE_DIR is not writable: {p}"


def test_logs_dir_can_be_created():
    """LOGS_DIR is set or defaults gracefully."""
    logs_dir = LOGS_DIR or "/tmp/deus_logs"
    p = Path(logs_dir) / "events"
    p.mkdir(parents=True, exist_ok=True)
    assert p.exists()


@pytest.mark.skipif(not CONFIG_SERVER, reason="CONFIG_SERVER not set — skipping")
def test_config_server_reachable():
    """CONFIG_SERVER responds to a basic GET request."""
    resp = requests.get(CONFIG_SERVER, timeout=5)
    assert resp.status_code < 500, f"CONFIG_SERVER returned {resp.status_code}"
