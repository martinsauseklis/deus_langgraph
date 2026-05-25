import inspect

import anthropic
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from agent.utils.logger import add_logger, logger
import asyncio


sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)

@add_logger
async def business_analyst_node(
    state: AgentState, config: RunnableConfig
) -> AgentState:
    sequence = state.get("sequence", [])
    sequence_step = sequence[0]

    try:
        response = await sonnet.ainvoke(
            input=[
                SystemMessage(
                    """You are a business analyst that translates customers' needs
                    into specific technical tasks to be passed to the UI/UX engineer.
                    Keep in mind that we are working currently on an existing Next.js
                    project. Don't assume anything else or offer to work on anything other.
                    Senior developer will have a context of the app, so you don't need to explain
                    the Next.js part."""
                ),
                *state["messages"],
                HumanMessage(sequence_step.prompt),
            ]
        )

        msg = AIMessage(response.content)
        msg.name = "business_analyst"
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
