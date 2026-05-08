

from typing import Annotated, Sequence, TypedDict, Literal
from langchain.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

class NodePrompts(BaseModel):
    node: Literal[
        "business_analyst_node", "ui_ux_node", "developer_node", "testing_node"
    ] = Field(description="Name of the node that will be executed. The names should be self explanatory about the role of each node")
    prompt: str = Field(description="""The prompt for the node containing 
                        the task and which is the next node that will 
                        receive the output of current node. Next node needed so the current node
                        can prepare results for that specific node better.""")


class PlannerOutput(BaseModel):
    next_nodes: list[NodePrompts] = Field(
        description="""A list of nodes that are going to be called next in the workflow.
                        List can contain one or more agents. 
                        If a task does not require input from other agents, you can just return a list with single item __end__""",
    )

class AgentState(TypedDict):
    create: bool
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    project_structure: dict  # full index, not injected raw into prompt
    tool_call_count: int
    testing_tool_call_count: int  # separate budget for testing agent
    sequence: PlannerOutput

