import os
from string import Template
from langchain.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_community.tools import ShellTool
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")
MAX_TOOL_CALLS = 25

sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)

sonnet_with_tools = sonnet.bind_tools([ShellTool()])


with open("./src/agent/utils/nodes/testing_node/SYSTEM_PROMPT.md") as file:
    SYSTEM_PROMPT_TEMPLATE = Template(file.read())


async def testing_node(state: AgentState, config: RunnableConfig) -> AgentState:
    sequence = state.get("sequence", [])
    sequence_step = sequence[0]
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

    if state.get("messages", [])[-1].type != "tool":
        model_input.append(HumanMessage(sequence_step.prompt))

    response = await tester.ainvoke(input=model_input)

    response.name = "testing_engineer"

    if len(response.tool_calls) == 0:
        sequence.pop(0)

    return {
        "messages": [response],
        "sequence": sequence,
        "testing_tool_call_count": state.get("testing_tool_call_count", 0)
        + len(response.tool_calls or []),
    }
