import os
from string import Template
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.nodes.developer_node.utils import structure_for_prompt
from agent.utils.state import AgentState
from agent.utils.model_config import MODEL_NAME
from langchain_core.runnables import RunnableConfig
from langchain_community.tools import ShellTool
from agent.utils.nodes.developer_node.tools.db_tool import db_tools
from langgraph.graph import END
import anthropic
import inspect
from agent.utils.logger import add_logger, logger
from agent.utils.nodes.developer_node.tools_node import developer_tools
import asyncio

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
MAX_TOOL_CALLS = 25

sonnet = ChatAnthropic(
    model_name=MODEL_NAME,
    streaming=True,
    max_retries=2,
)

with open("./src/agent/utils/nodes/developer_node/SYSTEM_PROMPT.md") as file:
    SYSTEM_PROMPT_TEMPLATE = Template(file.read())

@add_logger
async def developer_node(state: AgentState, config: RunnableConfig) -> AgentState:
    sonnet_with_tools = sonnet.bind_tools(developer_tools)

    # Always work from a copy so we never mutate shared state.
    sequence = list(state.get("sequence") or [])
    sequence_step = sequence[0]
    PROJ_PATH = f"{WORKSPACE_DIR}/{config['metadata']['thread_id']}"
    remaining_tool_calls = MAX_TOOL_CALLS - state.get("tool_call_count", 0)
    sen_dev = sonnet_with_tools if remaining_tool_calls > 0 else sonnet

    model_input = [
        SystemMessage(
            SYSTEM_PROMPT_TEMPLATE.substitute(
                project_path=PROJ_PATH,
                project_structure=structure_for_prompt(
                    state.get("project_structure", {})
                ),
                remaining_tool_calls=remaining_tool_calls,
                schema_name=config["metadata"]["thread_id"].replace("-", "_"),
            )
        ),
        *state["messages"],
    ]

    if state.get("messages", [])[-1].type != "tool":
        model_input.append(HumanMessage(sequence_step.prompt))
    try:
        response = await sen_dev.ainvoke(input=model_input)
        response.name = "senior_developer"

        # Advance sequence only when this step is complete (no more tool calls).
        new_sequence = sequence[1:] if not response.tool_calls else sequence

        return {
            "messages": [response],
            "sequence": new_sequence,
            "tool_call_count": state.get("tool_call_count", 0)
            + len(response.tool_calls or []),
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
