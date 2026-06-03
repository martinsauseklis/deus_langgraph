from typing import Literal
from langchain.messages import AIMessage, ToolMessage
from langgraph.types import Command
from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field


class BusinessAnalystOutput(BaseModel):
    next_node: Literal["ui_ux_node", "developer_node", "testing_node"] = Field(
        description="""
            When planning an actual development, you need to select appropriate next node that is going to be executed in the project 
            development cycle. The values are self explanatory what each node is in charge of.
        """
    )
    prompt_for_next_node: str = Field(
        description="The prompt telling the selected next node what do you want it to do."
    )


@tool(
    args_schema=BusinessAnalystOutput,
    description="The planning tool which allows business analyst to give tasks to other agents and provide prompt to the next agent",
)
def planning_tool(next_node: str, prompt_for_next_node: str, runtime: ToolRuntime):

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"Sending task to the agent {next_node}",
                    tool_call_id=runtime.tool_call_id,
                ),
            ],
            "tasks": [(next_node, prompt_for_next_node)],
        }
    )
