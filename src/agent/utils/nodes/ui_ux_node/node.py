import inspect

import anthropic
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.logger import add_logger
from agent.utils.state import AgentState
from agent.utils.model_config import MODEL_NAME
from langchain_core.runnables import RunnableConfig

sonnet = ChatAnthropic(
    model_name=MODEL_NAME,
    streaming=True,
    max_retries=2,
)

@add_logger
async def ui_ux_node(state: AgentState, config: RunnableConfig) -> AgentState:
    # Always work from a copy so we never mutate shared state.
    sequence = list(state.get("sequence") or [])
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

        return {"messages": [msg], "sequence": sequence[1:]}

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
