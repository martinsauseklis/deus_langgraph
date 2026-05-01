from langchain.messages import RemoveMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.nodes.summarization_node.utils import _flatten_ai_content
from agent.utils.state import AgentState

model = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=False,
    effort="medium",
    disable_streaming=True,
    tags=["langsmith:nostream"]
)

summarization_model = model.bind(max_tokens=500)


def summarization_node(state: AgentState):
    summary = state.get("summary", "")
    if summary:
        summary_message = (
            f"This is a summary of the conversation to date: {summary}\n\n"
            "Extend the summary by taking into account the new messages above:"
        )
    else:
        summary_message = "Create a summary of the conversation above:"

    # Only include human and AI messages; tool messages (tool_result) are skipped.
    # AI messages are flattened to plain text so no tool_use blocks reach the API.
    messages = []
    for msg in state["messages"]:
        if msg.type == "human":
            messages.append({"type": "human", "content": msg.content})
        elif msg.type == "ai":
            messages.append({"type": "ai", "content": _flatten_ai_content(msg)})

    messages.append({"type": "human", "content": summary_message})

    response = summarization_model.invoke(messages)
    response.id = f"do-not-render-{response.id}"
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-2]]
    return {"summary": response.content, "messages": delete_messages}
