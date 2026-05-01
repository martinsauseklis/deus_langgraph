from agent.utils.state import AgentState


def development_router(state: AgentState) -> str:
    last_message = state.get("messages", [])[-1]
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tools"

    sequence = state.get("sequence")
    if len(sequence) > 0:
        sequence_step = sequence[0].node
        return sequence_step
    
    return "__end__"