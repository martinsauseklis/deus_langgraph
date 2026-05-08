import inspect

import anthropic
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)


async def ui_ux_node(state: AgentState, config: RunnableConfig) -> AgentState:
    sequence = state.get("sequence", [])
    sequence_step = sequence[0]

    try:
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

    except anthropic.APIError as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with Anthropic API error: {e.message}"
                )
            ],
            "sequence": [],
        }

    except Exception as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with: {str(e)}"
                )
            ],
            "sequence": [],
        }