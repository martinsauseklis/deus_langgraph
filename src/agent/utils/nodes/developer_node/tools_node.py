from langchain_community.tools import ShellTool
from langgraph.prebuilt import ToolNode

developer_tools = ToolNode([ShellTool()])
