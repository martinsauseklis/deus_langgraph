from agent.utils.custom_nodes.custom_nodes import LoggedToolNode
from agent.utils.nodes.business_analyst_node.tools.planning_tool import planning_tool

business_analyst_tools = [planning_tool]
business_analyst_tools_node = LoggedToolNode(business_analyst_tools, handle_tool_errors=True)