from asyncio import CancelledError

from langchain.messages import ToolMessage
from langgraph.prebuilt import ToolNode

from agent.utils.logger import add_tool_logger


class LoggedToolNode(ToolNode):
    @add_tool_logger
    def invoke(self, *args, **kwargs):
        return super().invoke(*args, **kwargs)
    
    @add_tool_logger
    async def ainvoke(self, *args, **kwargs):
        return await super().ainvoke(*args, **kwargs)
    