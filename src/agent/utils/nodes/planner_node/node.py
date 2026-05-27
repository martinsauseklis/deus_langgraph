import inspect
import os
from string import Template
import anthropic
from langchain.messages import AIMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.state import AgentState, PlannerOutput
from agent.utils.model_config import MODEL_NAME
from langchain_core.runnables import RunnableConfig
from agent.utils.logger import add_logger, logger
import asyncio

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")

sonnet = ChatAnthropic(
    model_name=MODEL_NAME,
    streaming=True,
    max_retries=2,
)

sonnet_with_structure = sonnet.with_structured_output(PlannerOutput)

with open("./src/agent/utils/nodes/planner_node/SYSTEM_PROMPT.md") as file:
    SYSTEM_PROMPT_TEMPLATE = Template(file.read())


@add_logger
async def planner_node(state: AgentState, config: RunnableConfig) -> AgentState:

    try:
        response = await sonnet_with_structure.ainvoke(
            input=[
                SystemMessage(SYSTEM_PROMPT_TEMPLATE.template),
                *state.get("messages", []),
            ]
        )

        return {
            "sequence": response.next_nodes,
            "tool_call_count": 0,
            "testing_tool_call_count": 0,
        }

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
