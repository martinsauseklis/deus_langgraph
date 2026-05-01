from agent.utils.state import AgentState

async def reset_testing_budget_node(state: AgentState) -> AgentState:
    """Resets the testing tool call counter after a completed testing cycle."""
    return {"testing_tool_call_count": 0}
