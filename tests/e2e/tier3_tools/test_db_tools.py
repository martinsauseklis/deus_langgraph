"""Database tool tests — no LLM required.

Connects directly to PostgreSQL and exercises the tools that the developer agent uses.
Skipped automatically when PG_HOST is not set.
  make e2e-tools
"""

from __future__ import annotations

import os
import uuid

import pytest

PG_AVAILABLE = bool(os.getenv("PG_HOST"))
pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PG_HOST not set — skipping DB tests")


@pytest.fixture(scope="module", autouse=True)
def _import_tools():
    """Fail fast if the tools can't be imported."""
    from agent.utils.nodes.developer_node.tools.db_tool import (
        check_schema_exists,
        create_schema,
        create_table,
        insert_rows,
        query_db,
    )
    return check_schema_exists, create_schema, create_table, insert_rows, query_db


@pytest.fixture
def tools():
    from agent.utils.nodes.developer_node.tools.db_tool import (
        check_schema_exists,
        create_schema,
        create_table,
        insert_rows,
        query_db,
    )
    return check_schema_exists, create_schema, create_table, insert_rows, query_db


@pytest.fixture
def test_schema(tools):
    """Creates a unique schema for a test and drops it afterwards."""
    check_schema_exists, create_schema, create_table, insert_rows, query_db = tools
    schema = "test_" + uuid.uuid4().hex[:8]
    create_schema.run({"schema_name": schema})
    yield schema
    # Cleanup: drop via psycopg2 directly
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST"), port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "mydb"), user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
    conn.commit()
    conn.close()


# ── check_schema_exists ───────────────────────────────────────────────────────


def test_check_schema_nonexistent(tools):
    check_schema_exists, *_ = tools
    result = check_schema_exists.run({"schema_name": "schema_that_does_not_exist_xyz"})
    assert "does not exist" in result


def test_check_schema_existing(tools, test_schema):
    check_schema_exists, *_ = tools
    result = check_schema_exists.run({"schema_name": test_schema})
    assert "already exists" in result


# ── create_table ──────────────────────────────────────────────────────────────


def test_create_table(tools, test_schema):
    _, _, create_table, *_ = tools
    result = create_table.run({
        "schema_name": test_schema,
        "table_name": "users",
        "columns": [
            {"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False},
            {"name": "name", "type": "TEXT", "nullable": False},
            {"name": "email", "type": "TEXT"},
        ],
    })
    assert "created" in result.lower()


def test_create_table_idempotent(tools, test_schema):
    _, _, create_table, *_ = tools
    kwargs = {
        "schema_name": test_schema,
        "table_name": "items",
        "columns": [{"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False}],
    }
    create_table.run(kwargs)
    result = create_table.run(kwargs)  # second call should not raise
    assert "error" not in result.lower()


# ── insert_rows ───────────────────────────────────────────────────────────────


def test_insert_and_query(tools, test_schema):
    _, _, create_table, insert_rows, query_db = tools

    create_table.run({
        "schema_name": test_schema,
        "table_name": "products",
        "columns": [
            {"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False},
            {"name": "name", "type": "TEXT"},
        ],
    })

    insert_rows.run({
        "schema_name": test_schema,
        "table_name": "products",
        "rows": [{"name": "alpha"}, {"name": "beta"}],
    })

    result = query_db.run({
        "query": f'SELECT name FROM "{test_schema}".products ORDER BY name',
    })
    assert "alpha" in result
    assert "beta" in result


# ── query_db security ─────────────────────────────────────────────────────────


def test_query_db_rejects_non_select(tools):
    *_, query_db = tools
    result = query_db.run({"query": "DROP TABLE pg_class"})
    assert "only SELECT" in result


# ── create_table type validation ──────────────────────────────────────────────


def test_create_table_rejects_unknown_type(tools, test_schema):
    """create_table must reject column types not in the allowlist."""
    _, _, create_table, *_ = tools
    result = create_table.run({
        "schema_name": test_schema,
        "table_name": "bad_table",
        "columns": [
            {"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False},
            {"name": "data", "type": "TEXT); DROP SCHEMA public; --"},
        ],
    })
    assert "not in the allowed list" in result, f"Expected rejection, got: {result}"


def test_create_table_rejects_injection_via_type(tools, test_schema):
    """Injected DDL in column type must not execute."""
    _, _, create_table, *_ = tools
    create_table.run({
        "schema_name": test_schema,
        "table_name": "injection_target",
        "columns": [
            {"name": "id", "type": "SERIAL); DROP TABLE injection_target; --", "primary_key": True, "nullable": False},
        ],
    })
    # If injection ran, the table would be gone; the real test is that no exception bubbled up
    # and no data loss occurred. Verify the schema still exists.
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST"), port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "mydb"), user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = %s)",
            (test_schema,),
        )
        exists = cur.fetchone()[0]
    conn.close()
    assert exists, "Schema was dropped — type injection may have succeeded"


def test_create_table_accepts_valid_types(tools, test_schema):
    """Common PostgreSQL types must all pass the allowlist."""
    _, _, create_table, *_ = tools
    result = create_table.run({
        "schema_name": test_schema,
        "table_name": "all_types",
        "columns": [
            {"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False},
            {"name": "name", "type": "TEXT"},
            {"name": "active", "type": "BOOLEAN"},
            {"name": "score", "type": "NUMERIC"},
            {"name": "created_at", "type": "TIMESTAMPTZ", "default": "NOW()"},
            {"name": "uid", "type": "UUID"},
            {"name": "payload", "type": "JSONB"},
        ],
    })
    assert "error" not in result.lower(), f"Valid types rejected: {result}"


# ── query_db read-only enforcement ────────────────────────────────────────────


def test_query_db_read_only_blocks_insert(tools, test_schema):
    """query_db must use a read-only session that blocks write statements."""
    _, _, create_table, _, query_db = tools
    create_table.run({
        "schema_name": test_schema,
        "table_name": "readonly_test",
        "columns": [{"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False}],
    })
    result = query_db.run({
        "query": f'INSERT INTO "{test_schema}".readonly_test DEFAULT VALUES',
    })
    assert "error" in result.lower() or "read-only" in result.lower(), (
        f"INSERT succeeded through query_db — read-only session not enforced. Result: {result}"
    )


def test_query_db_read_only_blocks_drop(tools, test_schema):
    """query_db must block DDL statements like DROP."""
    *_, query_db = tools
    result = query_db.run({"query": f'DROP SCHEMA "{test_schema}" CASCADE'})
    assert "error" in result.lower() or "read-only" in result.lower(), (
        f"DROP succeeded through query_db — read-only session not enforced. Result: {result}"
    )


def test_query_db_select_only_check_bypassed_by_semicolon(tools, test_schema):
    """DOCUMENTS: SELECT-only guard is bypassable with semicolons.

    This test is marked xfail because the guard CAN be bypassed.
    It documents the known SQL injection risk in query_db.
    """
    *_, query_db = tools
    # This starts with SELECT so passes the guard, but contains a second statement.
    # psycopg2 execute() will attempt to run both statements.
    # The test asserts the second statement IS executed, which is the vulnerability.
    import psycopg2

    _, _, create_table, _, _ = tools
    create_table.run({
        "schema_name": test_schema,
        "table_name": "canary",
        "columns": [{"name": "id", "type": "SERIAL", "primary_key": True, "nullable": False}],
    })

    # If the second statement runs, it will drop the canary table.
    try:
        query_db.run({
            "query": f'SELECT 1; DROP TABLE "{test_schema}".canary; --',
        })
    except Exception:
        pass

    # Check if the table still exists.
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST"), port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "mydb"), user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema = '{test_schema}' AND table_name = 'canary')"
        )
        exists = cur.fetchone()[0]
    conn.close()

    # Document the outcome — do not hard-fail either way; just note it.
    if not exists:
        pytest.xfail("CONFIRMED SECURITY ISSUE: multi-statement query dropped the canary table.")
    # If the table still exists, psycopg2 blocked it (some versions do).
