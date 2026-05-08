from langchain.messages import AIMessage
from langgraph.errors import NodeError
from agent.utils.state import AgentState
from langgraph.types import Command
from langgraph.graph import END



def default_handler(state: AgentState, error: NodeError):
    return Command(
        goto=END,
        update={
            "messages": AIMessage(f"Node {error.node} failed with: {error.error}")
        }
    )