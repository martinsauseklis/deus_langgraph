from langchain_community.tools import ShellTool
from langgraph.prebuilt import ToolNode

testing_tools = ToolNode([ShellTool()])
