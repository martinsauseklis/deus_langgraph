import inspect
import os
from string import Template
import aiohttp
import anthropic
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_community.tools import ShellTool
from langgraph.graph import END
from agent.utils.logger import add_logger, logger
from agent.utils.state import AgentState
from agent.utils.model_config import MODEL_NAME
from langchain_core.runnables import RunnableConfig
from agent.utils.nodes.testing_node.tools_node import testing_tools

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")
MAX_TOOL_CALLS = 25

sonnet = ChatAnthropic(
    model_name=MODEL_NAME,
    streaming=True,
    max_retries=2,
)


with open("./src/agent/utils/nodes/testing_node/SYSTEM_PROMPT.md") as file:
    SYSTEM_PROMPT_TEMPLATE = Template(file.read())

@add_logger
async def testing_node(state: AgentState, config: RunnableConfig) -> AgentState:
    sonnet_with_tools = sonnet.bind_tools(testing_tools)
    # Always work from a copy so we never mutate shared state.
    PROJ_PATH = f"{WORKSPACE_DIR}/{config['metadata']['thread_id']}"
    thread_id = config["metadata"]["thread_id"]

    remaining_tool_calls = MAX_TOOL_CALLS - state.get("testing_tool_call_count", 0)
    tester = sonnet_with_tools if remaining_tool_calls > 0 else sonnet

    model_input = [
        SystemMessage(
            SYSTEM_PROMPT_TEMPLATE.substitute(
                project_structure=state.get(
                    "project_structure", "The structure is missing"
                ),
                remaining_tool_calls=remaining_tool_calls,
                config_server=CONFIG_SERVER,
                thread_id=thread_id,
                project_path=PROJ_PATH,
            )
        ),
        *state.get("messages", []),
    ]

    # if state.get("messages", [])[-1].type != "tool":
    #     model_input.append(HumanMessage(""))

    try:
        response = await tester.ainvoke(input=model_input)

        response.name = "testing_engineer"

        # Advance sequence and notify CONFIG_SERVER only when this step is done.
        if not response.tool_calls:
            if CONFIG_SERVER:
                try:
                    async with aiohttp.ClientSession(CONFIG_SERVER) as session:
                        async with session.get(f"/set_testable/{thread_id}") as res:
                            await res.read()
                            if res.status >= 400:
                                logger.warning(
                                    "set_testable returned %s for thread %s",
                                    res.status,
                                    thread_id,
                                    extra={"thread_id": thread_id},
                                )
                except aiohttp.ClientError as e:
                    logger.warning(
                        "set_testable request failed: %s",
                        e,
                        extra={"thread_id": thread_id},
                    )
        else:
            pass

        return {
            "messages": [response],
            "testing_tool_call_count": state.get("testing_tool_call_count", 0)
            + len(response.tool_calls or []),
            "prompt_for_next_node": None,
            "next_node": None
        }

    except anthropic.APIError as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with Anthropic API error: {e.message}"
                )
            ],
            "prompt_for_next_node": None,
            "next_node": None
        }

    except Exception as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with: {str(e)}"
                )
            ],
            "prompt_for_next_node": None,
            "next_node": None
        }
