import inspect

import anthropic
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END
from agent.utils.state import AgentState
from agent.utils.model_config import MODEL_NAME
from langchain_core.runnables import RunnableConfig
from agent.utils.logger import add_logger, logger
import asyncio


sonnet = ChatAnthropic(
    model_name=MODEL_NAME,
    streaming=True,
    max_retries=2,
)

@add_logger
async def business_analyst_node(
    state: AgentState, config: RunnableConfig
) -> AgentState:
    # Always work from a copy so we never mutate shared state.
    sequence = list(state.get("sequence") or [])
    sequence_step = sequence[0]

    try:
        response = await sonnet.ainvoke(
            input=[
                SystemMessage(
                    """You are a business analyst that translates customers' needs
                    into specific technical tasks to be passed to the UI/UX engineer.
                    Keep in mind that we are working currently on an existing Next.js
                    project. Don't assume anything else or offer to work on anything else.
                    Senior developer will have a context of the app, so you don't need to explain
                    the Next.js part."""
                ),
                *state["messages"],
                HumanMessage(sequence_step.prompt),
            ]
        )

        msg = AIMessage(response.content)
        msg.name = "business_analyst"

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
