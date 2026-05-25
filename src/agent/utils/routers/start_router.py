from agent.utils.state import AgentState
from langchain_core.messages.utils import count_tokens_approximately


MAX_TOKEN_COUNT_TO_TRIGGER_SUMMARY = 5000

def start_router(state: AgentState):
    if state.get("create"):
        return "setup_node"
    # if count_tokens_approximately(state["messages"]) > MAX_TOKEN_COUNT_TO_TRIGGER_SUMMARY:
    #     return "summarization_node"
    return "input_validation_node"
