"""
pg_tools.py
-----------
LangGraph-compatible Postgres tools for use with ToolNode.

Tools:
  - check_schema_exists   → check if a schema exists
  - create_schema         → create a schema
  - create_table          → create a table from a column spec
  - insert_rows           → batch insert rows
  - query_db              → run a SELECT query in a read-only transaction
"""

import json
import os
from typing import Optional

import psycopg2
import psycopg2.extras
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# ─── connection ───────────────────────────────────────────────────────────────


def get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "mydb"),
        user=os.getenv("PG_USER", "myuser"),
        password=os.getenv("PG_PASSWORD", "mypassword"),
    )


# ─── type allowlist ───────────────────────────────────────────────────────────

# LLM-supplied column types are validated against this set before being
# interpolated into DDL. This prevents SQL injection via crafted type strings.
_ALLOWED_PG_TYPES: frozenset[str] = frozenset({
    "TEXT", "VARCHAR", "CHAR", "BPCHAR",
    "BOOLEAN", "BOOL",
    "INTEGER", "INT", "INT2", "INT4", "INT8", "BIGINT", "SMALLINT",
    "SERIAL", "BIGSERIAL", "SMALLSERIAL",
    "FLOAT", "FLOAT4", "FLOAT8", "DOUBLE PRECISION", "REAL",
    "NUMERIC", "DECIMAL", "MONEY",
    "DATE", "TIME", "TIMESTAMP", "TIMESTAMPTZ", "TIMETZ",
    "INTERVAL", "UUID", "JSON", "JSONB", "BYTEA", "OID",
    "CITEXT", "INET", "CIDR", "MACADDR",
})


def _pg_type_is_safe(type_str: str) -> bool:
    """Return True if type_str is a recognised PostgreSQL base type."""
    # Strip precision/scale (e.g. VARCHAR(255) → VARCHAR, NUMERIC(10,2) → NUMERIC)
    # and array brackets (e.g. TEXT[] → TEXT).
    base = type_str.strip().upper().split("(")[0].split("[")[0].strip()
    return base in _ALLOWED_PG_TYPES


# ─── input schemas ────────────────────────────────────────────────────────────


class CheckSchemaInput(BaseModel):
    schema_name: str = Field(description="Postgres schema name to check for existence")


class CreateSchemaInput(BaseModel):
    schema_name: str = Field(description="Postgres schema name to create")
    if_not_exists: bool = Field(default=True)


class ColumnSpec(BaseModel):
    name: str = Field(description="Column name")
    type: str = Field(
        description="Postgres type e.g. TEXT, INTEGER, UUID, JSONB, TIMESTAMPTZ, SERIAL"
    )
    nullable: bool = Field(default=True)
    default: Optional[str] = Field(
        default=None, description="SQL default expression e.g. NOW() or 'pending'"
    )
    primary_key: bool = Field(default=False)


class CreateTableInput(BaseModel):
    schema_name: str
    table_name: str
    columns: list[ColumnSpec] = Field(
        description="List of column definitions",
        examples=[
            [
                {
                    "name": "id",
                    "type": "SERIAL",
                    "primary_key": True,
                    "nullable": False,
                },
                {"name": "name", "type": "TEXT", "nullable": False},
                {"name": "status", "type": "TEXT", "default": "'active'"},
                {"name": "created_at", "type": "TIMESTAMPTZ", "default": "NOW()"},
            ]
        ],
    )
    if_not_exists: bool = Field(default=True)


class InsertRowsInput(BaseModel):
    schema_name: str
    table_name: str
    rows: list[dict] = Field(
        description="List of dicts where keys are column names. All rows must have the same keys.",
        examples=[
            [
                {"name": "Alice", "status": "active"},
                {"name": "Bob", "status": "pending"},
            ]
        ],
    )
    returning: Optional[str] = Field(
        default=None,
        description="Column name to return after insert, e.g. 'id'",
    )


class QueryInput(BaseModel):
    query: str = Field(
        description="A SELECT SQL query to execute. Only SELECT statements are allowed.",
        examples=["SELECT * FROM myschema.users WHERE status = 'active' LIMIT 10"],
    )
    params: Optional[list] = Field(
        default=None,
        description="Optional list of query parameters for parameterized queries e.g. ['active', 5]",
    )


# ─── tools ────────────────────────────────────────────────────────────────────


@tool("check_schema_exists", args_schema=CheckSchemaInput)
def check_schema_exists(schema_name: str) -> str:
    """Check whether a Postgres schema exists.

    Call this before create_schema to avoid redundant operations.
    """
    sql = "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = %s);"
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (schema_name,))
            exists = cur.fetchone()[0]
        return f"Schema '{schema_name}' {'already exists' if exists else 'does not exist'}."
    except Exception as e:
        return f"Error checking schema: {e}"
    finally:
        if conn:
            conn.close()


@tool("create_schema", args_schema=CreateSchemaInput)
def create_schema(schema_name: str, if_not_exists: bool = True) -> str:
    """Create a Postgres schema.

    Always call check_schema_exists first to confirm the schema is not already present.
    """
    qualifier = "IF NOT EXISTS" if if_not_exists else ""
    sql = f'CREATE SCHEMA {qualifier} "{schema_name}";'
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        return f"Schema '{schema_name}' created successfully."
    except Exception as e:
        if conn:
            conn.rollback()
        return f"Error creating schema: {e}"
    finally:
        if conn:
            conn.close()


@tool("create_table", args_schema=CreateTableInput)
def create_table(
    schema_name: str,
    table_name: str,
    columns: list[dict],
    if_not_exists: bool = True,
) -> str:
    """Create a table inside an existing Postgres schema from a column spec.

    Column dict fields:
      name        (str)       — column name
      type        (str)       — Postgres type: TEXT, INTEGER, SERIAL, UUID, JSONB, TIMESTAMPTZ, etc.
      nullable    (bool)      — default True
      default     (str|None)  — SQL default expression e.g. "NOW()" or "'pending'"
      primary_key (bool)      — default False
    """
    col_specs = [c if isinstance(c, ColumnSpec) else ColumnSpec(**c) for c in columns]

    # Validate every column type before building any SQL.
    for c in col_specs:
        if not _pg_type_is_safe(c.type):
            return (
                f"Error: column type '{c.type}' is not in the allowed list. "
                "Use standard PostgreSQL types such as TEXT, INTEGER, SERIAL, UUID, "
                "JSONB, TIMESTAMPTZ, BOOLEAN, NUMERIC, etc."
            )

    col_defs = []
    for c in col_specs:
        parts = [f'"{c.name}"', c.type]
        if c.primary_key:
            parts.append("PRIMARY KEY")
        if not c.nullable and not c.primary_key:
            parts.append("NOT NULL")
        if c.default is not None:
            parts.append(f"DEFAULT {c.default}")
        col_defs.append(" ".join(parts))

    qualifier = "IF NOT EXISTS" if if_not_exists else ""
    sql = (
        f'CREATE TABLE {qualifier} "{schema_name}"."{table_name}" '
        f"({', '.join(col_defs)});"
    )
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        return f"Table '{schema_name}.{table_name}' created.\nDDL: {sql}"
    except Exception as e:
        if conn:
            conn.rollback()
        return f"Error creating table: {e}"
    finally:
        if conn:
            conn.close()


@tool("insert_rows", args_schema=InsertRowsInput)
def insert_rows(
    schema_name: str,
    table_name: str,
    rows: list[dict],
    returning: Optional[str] = None,
) -> str:
    """Batch insert one or more rows into a Postgres table.

    All rows must have the same keys (column names).
    Use the 'returning' field to get back generated values like 'id'.
    """
    if not rows:
        return "No rows provided — nothing inserted."

    columns = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in columns)
    values = [tuple(row[c] for c in columns) for row in rows]
    ret_clause = f" RETURNING {returning}" if returning else ""
    sql = (
        f'INSERT INTO "{schema_name}"."{table_name}" ({col_list}) '
        f"VALUES %s{ret_clause};"
    )
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, values)
            returned = [r[0] for r in cur.fetchall()] if returning else None
        conn.commit()
        if returning:
            return (
                f"Inserted {len(rows)} row(s) into '{schema_name}.{table_name}'. "
                f"Returned {returning}s: {returned}"
            )
        return f"Inserted {len(rows)} row(s) into '{schema_name}.{table_name}'."
    except Exception as e:
        if conn:
            conn.rollback()
        return f"Error inserting rows: {e}"
    finally:
        if conn:
            conn.close()


@tool("query_db", args_schema=QueryInput)
def query_db(query: str, params: Optional[list] = None) -> str:
    """Execute a SELECT query and return results as a JSON string.

    Runs in a read-only transaction — any write statement will be rejected
    by the database regardless of the query text.
    Use parameterized queries to pass values safely:
      query:  "SELECT * FROM myschema.orders WHERE status = %s"
      params: ["shipped"]
    """
    conn = None
    try:
        conn = get_conn()
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params or [])
            rows = cur.fetchall()
            result = [dict(r) for r in rows]
        return json.dumps(result, default=str)
    except Exception as e:
        return f"Error querying database: {e}"
    finally:
        if conn:
            conn.close()


# ─── export ───────────────────────────────────────────────────────────────────

db_tools = [
    check_schema_exists,
    create_schema,
    create_table,
    insert_rows,
    query_db,
]
