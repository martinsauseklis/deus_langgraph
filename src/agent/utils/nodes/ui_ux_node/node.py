from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.logger import add_logger
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)

@add_logger
async def ui_ux_node(state: AgentState, config: RunnableConfig) -> AgentState:

    sequence = state.get("sequence", [])
    sequence_step = sequence[0]
    response = await sonnet.ainvoke(
        input=[
            SystemMessage(
                """You are a master UI/UX engineer. Based on the business analyst's
input, provide an outline of UI libraries and layouts the senior developer must use.
The project is a Next.js app."""
            ),
            *state["messages"],
            HumanMessage(sequence_step.prompt),
        ]
    )
    msg = AIMessage(response.content)
    msg.name = "ui_ux_engineer"
    sequence.pop(0)

    return {"messages": [msg], "sequence": sequence}
