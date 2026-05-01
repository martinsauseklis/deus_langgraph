from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)


async def business_analyst_node(
    state: AgentState, config: RunnableConfig
) -> AgentState:
    sequence = state.get("sequence", [])
    sequence_step = sequence[0]
    response = await sonnet.ainvoke(
        input=[
            SystemMessage("""You are a business analyst that translates customers' needs
into specific technical tasks to be passed to the UI/UX engineer.
                          Keep in mind that we are working currently on an existing Next.js
                          project. Don't assume anything else or offer to work on anything other.
                          Senior developer will have a context of the app, so you don't need to explain
                          the Next.js part."""),
            *state["messages"],
            HumanMessage(sequence_step.prompt),
        ]
    )
    msg = AIMessage(response.content)
    msg.name = "business_analyst"
    updated_sequence = sequence[-len(sequence) + 1 :]
    return {"messages": [msg], "sequence": updated_sequence}
