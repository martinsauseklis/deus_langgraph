from langchain_community.tools import ShellTool
from agent.utils.custom_nodes.custom_nodes import LoggedToolNode

developer_tools = LoggedToolNode([ShellTool()])
