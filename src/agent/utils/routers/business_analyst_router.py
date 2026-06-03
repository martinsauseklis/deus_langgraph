from langchain.messages import HumanMessage

from agent.utils.state import AgentState
from langgraph.types import Send


def business_analyst_router(state: AgentState):
    return [
        Send(
            prompt[0],
            {**state, "messages": state["messages"] + [HumanMessage(prompt[1])]},
        )
        for prompt in state["tasks"]
    ]
