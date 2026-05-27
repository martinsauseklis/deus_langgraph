"""Routing logic unit tests — pure Python, no LLM, no HTTP.

Tests the three router functions directly to catch logic regressions cheaply.
  make e2e-routing
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.utils.routers.development_router import development_router
from agent.utils.routers.start_router import start_router
from agent.utils.state import NodePrompts


# ── start_router ───────────────────────────────────────────────────────────────


def test_start_router_create_true_routes_to_setup():
    state = {"create": True, "messages": [HumanMessage("hello")]}
    assert start_router(state) == "setup_node"


def test_start_router_create_false_routes_to_validation():
    state = {"create": False, "messages": [HumanMessage("hello")]}
    assert start_router(state) == "input_validation_node"


def test_start_router_missing_create_routes_to_validation():
    state = {"messages": [HumanMessage("hello")]}
    assert start_router(state) == "input_validation_node"


# ── development_router ────────────────────────────────────────────────────────


def test_development_router_pending_tool_calls_returns_tools():
    """If the last message has tool_calls, router must return 'tools'."""
    ai_msg = AIMessage(content="", tool_calls=[{"id": "tc1", "name": "shell", "args": {}}])
    state = {
        "messages": [ai_msg],
        "sequence": [NodePrompts(node="developer_node", prompt="do stuff")],
    }
    assert development_router(state) == "tools"


def test_development_router_no_tool_calls_follows_sequence():
    """With no pending tool calls, router advances to the first sequence node."""
    ai_msg = AIMessage(content="done")
    state = {
        "messages": [ai_msg],
        "sequence": [NodePrompts(node="testing_node", prompt="run tests")],
    }
    assert development_router(state) == "testing_node"


def test_development_router_empty_sequence_returns_end():
    ai_msg = AIMessage(content="done")
    state = {"messages": [ai_msg], "sequence": []}
    assert development_router(state) == "__end__"


def test_development_router_routes_to_each_valid_node():
    for node_name in ("business_analyst_node", "ui_ux_node", "developer_node", "testing_node"):
        ai_msg = AIMessage(content="")
        state = {
            "messages": [ai_msg],
            "sequence": [NodePrompts(node=node_name, prompt="task")],
        }
        assert development_router(state) == node_name


# ── input_validation_node ─────────────────────────────────────────────────────
# These tests invoke the node function directly (async) without the LangGraph runtime.


import asyncio
from agent.utils.nodes.input_validation_node.node import input_validation_node


def _sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_input_validation_no_orphans_returns_nothing():
    """When there are no orphaned tool calls, node returns nothing (no state change)."""
    state = {"messages": [HumanMessage("hello")], "sequence": []}
    config = {"metadata": {"thread_id": "test-" + str(uuid4())}}
    result = _sync(input_validation_node(state, config=config))
    assert not result  # None or empty dict — no state change needed


def test_input_validation_adds_missing_tool_message():
    """If an AI message has a tool call with no matching ToolMessage, node patches it."""
    tool_call_id = "missing-tc-" + str(uuid4())
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"id": tool_call_id, "name": "shell", "args": {"commands": "ls"}}],
    )
    state = {"messages": [ai_msg], "sequence": []}
    config = {"metadata": {"thread_id": "test-" + str(uuid4())}}
    result = _sync(input_validation_node(state, config=config))

    assert result is not None
    patched = result.get("messages", [])
    assert len(patched) == 1
    assert patched[0].tool_call_id == tool_call_id


def test_input_validation_does_not_duplicate_existing_tool_message():
    """When a ToolMessage already exists for a tool call, node leaves it alone."""
    tool_call_id = "existing-tc-" + str(uuid4())
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"id": tool_call_id, "name": "shell", "args": {}}],
    )
    tool_msg = ToolMessage(content="result", tool_call_id=tool_call_id)
    state = {"messages": [ai_msg, tool_msg], "sequence": []}
    config = {"metadata": {"thread_id": "test-" + str(uuid4())}}
    result = _sync(input_validation_node(state, config=config))
    assert not result


# ── Sequence immutability ──────────────────────────────────────────────────────


def test_development_router_does_not_mutate_input_state():
    """Router must read sequence without modifying the state it was passed."""
    original = [NodePrompts(node="developer_node", prompt="do it")]
    ai_msg = AIMessage(content="done")
    state = {"messages": [ai_msg], "sequence": original}

    development_router(state)

    # The original list must be unchanged — the router only reads, never pops.
    assert len(original) == 1, "development_router mutated the sequence list"


def test_sequence_list_is_not_shared_across_calls():
    """Two independent states must not share the same sequence list object."""
    seq_a = [NodePrompts(node="developer_node", prompt="a")]
    seq_b = [NodePrompts(node="testing_node", prompt="b")]
    assert seq_a is not seq_b

    ai_a = AIMessage(content="")
    ai_b = AIMessage(content="")
    state_a = {"messages": [ai_a], "sequence": seq_a}
    state_b = {"messages": [ai_b], "sequence": seq_b}

    result_a = development_router(state_a)
    result_b = development_router(state_b)

    assert result_a == "developer_node"
    assert result_b == "testing_node"
    # Verify neither state was modified.
    assert len(seq_a) == 1
    assert len(seq_b) == 1
