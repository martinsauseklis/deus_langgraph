from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from typing import TypedDict, Annotated
from langchain.messages import AnyMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from shutil import copytree
from langgraph.runtime import Runtime
from operator import add
from dataclasses import dataclass
import subprocess
import asyncio


@dataclass
class Context:
    user_id: str


class AgentState(TypedDict):
    create: bool
    thread_id: str
    node_installed: int


def check_if_create(state: AgentState) -> str:
    return state["create"]


def create_config(state: AgentState, config: RunnableConfig, runtime: Runtime[Context]) -> AgentState:
    return {
        "thread_id": config["metadata"]["thread_id"]
    }


def update_config(state: AgentState) -> AgentState:
    return state


def copy_files(state: AgentState) -> AgentState:
    # copytree("workspace/template", "workspace/" + state["thread_id"])
    return state


async def install_node_modules(state: AgentState) -> AgentState:
    run = subprocess.run(["npm.cmd", "install"], cwd="workspace/template")

    return {
        "node_installed": run.returncode
    }


def run_dev_server(state: AgentState) -> AgentState:
    process = subprocess.Popen(
        ["npm.cmd", "run", "dev"], cwd="workspace/template")
    print(process.pid)
    print("started dev server")
    return state


workflow = StateGraph(AgentState, context_schema=Context)
workflow.add_node("create_config", create_config)
workflow.add_node("update_config", update_config)
workflow.add_node("copy_files", copy_files)
workflow.add_node("install_node_modules", install_node_modules)
workflow.add_node("run_dev_server", run_dev_server)

workflow.add_conditional_edges(START, check_if_create, {
                               True: "create_config", False: "update_config"})
workflow.add_edge("create_config", "copy_files")
workflow.add_edge("copy_files", "install_node_modules")
workflow.add_edge("install_node_modules", "run_dev_server")
workflow.add_edge("run_dev_server", END)
workflow.add_edge("update_config", "run_dev_server")
workflow.add_edge("run_dev_server", END)
graph = workflow.compile()
