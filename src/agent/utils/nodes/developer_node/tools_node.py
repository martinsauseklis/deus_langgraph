from langchain_community.tools import ShellTool
from agent.utils.custom_nodes.custom_nodes import LoggedToolNode
from agent.utils.nodes.developer_node.tools.db_tool import db_tools


developer_tools = [ShellTool(), *db_tools]
developer_tools_node = LoggedToolNode(developer_tools, handle_tool_errors=True)
