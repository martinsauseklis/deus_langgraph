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

    try:
        response = await sonnet.ainvoke(
            input=[
                SystemMessage(
                    """You are a master UI/UX engineer. Based on the business analyst's
                    input, provide information that would make the project a UI/UX success.
                    The project is a Next.js app. The response
                    will be consumed by another AI agent. So create whatever transfers your output to next
                    agent the best. 
                    
                    Keep the responses as concise as needed, do not generate full code as that is the task of the developer. Just
                    generate hints for the developer AI agent. They dont have to be user friendly, they need to be AI friendly."""
                ),
                *state["messages"],
                # HumanMessage(state["prompt_for_next_node"]),
            ]
        )
        msg = AIMessage(response.content)
        msg.name = "ui_ux_engineer"

        return {
            "messages": [msg],
            "prompt_for_next_node": None,
            "next_node": None,
        }

    except anthropic.APIError as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with Anthropic API error: {e.message}"
                )
            ],
            "prompt_for_next_node": None,
            "next_node": None,
        }

    except Exception as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with: {str(e)}"
                )
            ],
            "prompt_for_next_node": None,
            "next_node": None,
        }
