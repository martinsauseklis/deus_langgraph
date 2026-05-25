from langchain_community.tools import ShellTool
from langgraph.prebuilt import ToolNode

testing_tools = [ShellTool()]
testing_tools_node = ToolNode(testing_tools, handle_tool_errors=True)