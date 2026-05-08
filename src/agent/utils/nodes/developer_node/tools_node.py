from langchain_community.tools import ShellTool
from langgraph.prebuilt import ToolNode
from agent.utils.nodes.developer_node.tools.db_tool import db_tools

developer_tools = ToolNode([ShellTool(), *db_tools])
