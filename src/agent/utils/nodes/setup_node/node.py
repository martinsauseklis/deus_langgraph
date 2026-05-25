import os
import aiohttp
from langchain.messages import AIMessage
from agent.utils.logger import add_logger
from agent.utils.state import AgentState
from langchain_core.runnables import RunnableConfig

CONFIG_SERVER = os.getenv("CONFIG_SERVER")

@add_logger
async def setup_node(state: AgentState, config: RunnableConfig):
    metadata = config.get("metadata")
    request_body = {
        "thread_id": metadata.get("thread_id"),
        "config_name": metadata.get("config_name"),
        "config_author": metadata.get("config_author"),
    }
    async with aiohttp.ClientSession(CONFIG_SERVER) as session:
        async with session.post("/create", json=request_body) as response:
            return {
                "messages": [AIMessage(content="The setup is done. You can run the server.")],
            }