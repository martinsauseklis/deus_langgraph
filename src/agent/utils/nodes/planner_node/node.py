import os
from string import Template
from typing import Literal, Sequence, Union
from langchain.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from agent.utils.nodes.developer_node.utils import structure_for_prompt
from agent.utils.state import AgentState, PlannerOutput
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

sonnet_with_structure = sonnet.with_structured_output(PlannerOutput)

with open("./src/agent/utils/nodes/planner_node/SYSTEM_PROMPT.md") as file:
    SYSTEM_PROMPT_TEMPLATE = Template(file.read())


async def planner_node(state: AgentState, config: RunnableConfig) -> AgentState:
    response = await sonnet_with_structure.ainvoke(
        input=[
            SystemMessage(SYSTEM_PROMPT_TEMPLATE.template),
            *state.get("messages", []),
        ]
    )

    return {"sequence": response.next_nodes}
