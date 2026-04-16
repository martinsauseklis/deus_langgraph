from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from typing import Literal, TypedDict, Annotated
from langchain.messages import AnyMessage, AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_anthropic import ChatAnthropic
from langgraph.runtime import Runtime
from langchain_anthropic import ChatAnthropic
from langchain.agents.middleware import ModelRequest, ShellToolMiddleware, HostExecutionPolicy, dynamic_prompt
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from dataclasses import dataclass
from operator import add
import asyncio
import aiohttp
import os
import json

NPM_PATH = os.getenv("NPM_PATH")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")

@dataclass
class Context:
    subdirectory: str

@dynamic_prompt
def context_aware_prompt(request: ModelRequest):
    subdirectory = request.runtime.context.subdirectory

    return f"""You are a master senior developer. 
        As such you operate only in the subdirectory called {subdirectory}.
        You cannot and must not under no circumstances operate outside the subdirectory.
        Before using shell tool always make sure you are withing the subdirectory. You can 
        run commands within nested directories but not in parent directory.
        Do NOT RUN the .sh files in the directory. Those are meant for user to execute from 
        the UI.
        """

sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    effort="high",
    max_retries=2,
)

coding_agent = create_agent(
    model=sonnet,
    middleware=[
        ShellToolMiddleware(
            workspace_root=WORKSPACE_DIR,
            execution_policy=HostExecutionPolicy()
        ),
        context_aware_prompt
    ],
    context_schema=Context,
)

class AgentState(TypedDict):
    create: bool = False
    messages: Annotated[list[AnyMessage], add] = []

def is_create(state: AgentState):
    if state["create"]:
        print("teh satet", state)
        return "setup"

    return "process_input"

async def setup(state: AgentState, config: RunnableConfig): 
    metadata = config.get("metadata")
    thread_id = metadata.get("thread_id")
    config_name = metadata.get("config_name")
    config_author = metadata.get("config_author")
    
    request_body = {
        "thread_id": thread_id,
        "config_name": config_name,
        "config_author": config_author
    }
    print("In setup")
    async with aiohttp.ClientSession(CONFIG_SERVER) as session:
        async with session.post("/create", json=request_body) as response:
            return {
                "create": False,
                "messages": [AIMessage(content="The setup is done. You can run the server.")]
            }
    


async def process_input(state: AgentState, config: RunnableConfig):

    response = await coding_agent.ainvoke(
        input={
            "messages": state["messages"]
        },
        context=Context(config["metadata"]["thread_id"]),
    )
    
    
    return {
        "messages": [AIMessage(content="Danonki")]
    }


workflow = StateGraph(AgentState)
workflow.add_node("setup", setup)
workflow.add_node("process_input", process_input)

workflow.add_conditional_edges(START, is_create, {
    "setup": "setup",
    "process_input": "process_input"
})
workflow.add_edge("setup", END)
workflow.add_edge("process_input", END)
graph = workflow.compile()
