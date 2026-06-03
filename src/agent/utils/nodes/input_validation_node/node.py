from typing import List

from langchain.messages import AIMessage, HumanMessage, SystemMessage
from agent.utils.logger import add_logger
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from uuid import uuid4
from langchain_core.messages import AIMessage, ToolMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig


@add_logger
async def input_validation_node(
    state: AgentState,
    config: RunnableConfig,
) -> AgentState:
    tool_messages: List[ToolMessage] = []
    messages = state.get("messages", [])[::-1]
    last_ai_with_tools = next(
        (
            msg
            for msg in messages
            if hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0
        ),
        None,
    )

    if last_ai_with_tools:
        for tool_call in last_ai_with_tools.tool_calls:
            id = tool_call.get("id")
            tool_message = next(
                (
                    msg
                    for msg in state["messages"]
                    if msg.type == "tool" and msg.tool_call_id == id
                ),
                None,
            )
            if not tool_message:
                tool_msg = ToolMessage(
                    content="Tool result missing", id=str(uuid4()), tool_call_id=id
                )
                tool_messages.append(tool_msg)

    if tool_messages:
        return {
            "messages": tool_messages,
        }
