from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from typing import Literal, TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain.messages import AnyMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from shutil import copytree
from langgraph.runtime import Runtime
from operator import add
from dataclasses import dataclass
import asyncio
import os
from utils.find_free_port import find_port

NPM_PATH = os.getenv("NPM_PATH")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")

@dataclass
class Context:
    pass

class AgentState(TypedDict):
    create: bool
    thread_id: str
    server_port: str | None
    messages: Annotated[list[AnyMessage], add_messages]
    stop_server: Literal[True] | None

def check_if_create(state: AgentState) -> str:
    if(state.get("stop_server", None)):
        return "stop_server"

    if(state["create"]):
        return "copy_files"
    
    if(state.get("server_port", None) != None):
        return "process_message"
    
    else:
        return "run_dev_server"


def copy_files(state: AgentState, config: RunnableConfig):
    copytree("workspace/template", "workspace/" + config["metadata"]["thread_id"])


async def install_node_modules(state: AgentState, config: RunnableConfig):   
    run = await asyncio.create_subprocess_exec(NPM_PATH, "install", cwd=f"workspace/{config["metadata"]["thread_id"]}")
    await run.wait()
    return {
        "create": False
    }
    


async def run_dev_server(state: AgentState, config: RunnableConfig) -> AgentState:
    port = str(find_port())
        
    process =  await asyncio.create_subprocess_exec("./start_server.sh", port, cwd=f"workspace/{config["metadata"]["thread_id"]}")
    
    return {
        "server_port": port
    }

def process_message(state: AgentState) -> AgentState:
    return {
        "messages": [
            AIMessage(f"The human message was: '{state['messages'][-1].content[0].get("text")}'")
        ]
    }

async def stop_server(state: AgentState, config: RunnableConfig) -> AgentState:
    process =  await asyncio.create_subprocess_exec("./stop_server.sh", state["server_port"], cwd=f"workspace/{config["metadata"]["thread_id"]}")
    return {
        "server_port": None,
        "stop_server": None
    }


workflow = StateGraph(AgentState)
workflow.add_node("copy_files", copy_files)
workflow.add_node("install_node_modules", install_node_modules)
workflow.add_node("run_dev_server", run_dev_server)
workflow.add_node("process_message", process_message)
workflow.add_node("stop_server", stop_server)

workflow.add_conditional_edges(START, check_if_create, {
                               "copy_files": "copy_files", "run_dev_server": "run_dev_server", "process_message": "process_message", "stop_server": "stop_server"})
workflow.add_edge("copy_files", "install_node_modules")
workflow.add_edge("install_node_modules", "run_dev_server")
workflow.add_edge("run_dev_server", "process_message")
workflow.add_edge("process_message", END)
workflow.add_edge("stop_server", END)
graph = workflow.compile()
