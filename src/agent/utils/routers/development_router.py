from agent.utils.state import AgentState


def development_router(state: AgentState) -> str:
    last_message = state.get("messages", [])[-1]
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tools"

    return state["next_node"]
    