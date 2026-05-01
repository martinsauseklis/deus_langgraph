from langchain.messages import AIMessage, HumanMessage
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from agent.utils.state import AgentState


sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)

class SendToDev(BaseModel):
    send_to_dev: bool = Field(description="If the input contains instructions to dev about failed tests, this should be true. If not - false")


async def testing_router(state: AgentState):
    """Single router for the testing node.
    
    Priority 1: if the last message has pending tool calls, go to testing_tools.
    Priority 2: use structured output to decide whether to loop back to senior_developer.
    
    Combining both decisions here avoids the duplicate add_conditional_edges error
    and ensures tool_use blocks always have matching tool_result blocks before we
    invoke the structured model.
    """
    last_msg = state.get("messages")[-1]

    # If the testing engineer made tool calls, execute them first.
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "testing_tools"

    # No pending tool calls — safe to invoke structured model.
    # Strip any residual tool_calls metadata so the Anthropic API never receives
    # a tool_use block without a following tool_result block.
    structured_model = sonnet.with_structured_output(SendToDev)
    clean_msg = AIMessage(
        content=last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content),
        name=getattr(last_msg, "name", None),
    )
    structured = await structured_model.ainvoke(input=[
        clean_msg,
        HumanMessage("Evaluate the input and return a proper value.")
    ])

    if structured.send_to_dev:
        return "developer_node"

    # Testing run is complete — reset the budget for the next cycle.
    # We return END here; the reset happens via the state update in the node itself,
    # but we need to signal it. Instead we handle the reset directly in the router
    # by returning a sentinel that maps to a thin reset node.
    return "reset_testing_budget_node"
