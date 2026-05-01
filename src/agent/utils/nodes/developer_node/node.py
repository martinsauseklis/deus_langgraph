import os
from string import Template
from langchain.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.nodes.developer_node.utils import structure_for_prompt
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langchain_community.tools import ShellTool
from langgraph.types import Command

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
MAX_TOOL_CALLS = 25

sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)

sonnet_with_tools = sonnet.bind_tools([ShellTool()])


with open("./src/agent/utils/nodes/developer_node/SYSTEM_PROMPT.md") as file:
    SYSTEM_PROMPT_TEMPLATE = Template(file.read())


async def developer_node(state: AgentState, config: RunnableConfig) -> AgentState:
    sequence = state.get("sequence", [])
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
            )
        ),
        *state["messages"],
    ]

    if state.get("messages", [])[-1].type != "tool":
        model_input.append(HumanMessage(sequence_step.prompt))

    response = await sen_dev.ainvoke(input=model_input)

    response.name = "senior_developer"

    if len(response.tool_calls) == 0:
        sequence.pop(0)
        
    return {
        "messages": [response],
        "sequence": sequence,
        "tool_call_count": state.get("tool_call_count", 0)
        + len(response.tool_calls or []),
    }
