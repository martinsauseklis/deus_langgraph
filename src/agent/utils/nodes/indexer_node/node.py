import asyncio
import os

from langgraph.graph import END
from agent.utils.nodes.indexer_node.project_parser import run_indexer
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")


async def indexer_node(state: AgentState, config: RunnableConfig) -> AgentState:
    PROJ_PATH = f"{WORKSPACE_DIR}/{config['metadata']['thread_id']}"
    project_structure = await asyncio.to_thread(
        run_indexer, PROJ_PATH, f"{PROJ_PATH}/ts_index.json"
    )

    return {"project_structure": project_structure}
