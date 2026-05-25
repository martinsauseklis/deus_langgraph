from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition
from agent.utils.nodes.input_validation_node.node import input_validation_node
from agent.utils.nodes.planner_node.node import planner_node
from agent.utils.nodes.reset_testing_budget_node.node import reset_testing_budget_node
from agent.utils.nodes.testing_node.node import testing_node
from agent.utils.nodes.business_analyst_node.node import business_analyst_node
from agent.utils.nodes.developer_node.node import developer_node
from agent.utils.nodes.developer_node.tools_node import developer_tools_node
from agent.utils.nodes.indexer_node.node import indexer_node
from agent.utils.nodes.summarization_node.node import summarization_node
from agent.utils.nodes.testing_node.tools_node import testing_tools_node
from agent.utils.nodes.setup_node.node import setup_node
from agent.utils.nodes.ui_ux_node.node import ui_ux_node
from langgraph.checkpoint.memory import MemorySaver
from agent.utils.routers.development_router import development_router
from agent.utils.routers.start_router import start_router
from agent.utils.routers.testing_router import testing_router
from agent.utils.state import AgentState


workflow = StateGraph(AgentState)
workflow.add_node("planner_node", planner_node)
workflow.add_node("input_validation_node", input_validation_node)
workflow.add_node("setup_node", setup_node)
workflow.add_node("business_analyst_node", business_analyst_node)
workflow.add_node("ui_ux_node", ui_ux_node)
workflow.add_node("developer_node", developer_node)
workflow.add_node("developer_tools", developer_tools_node)
workflow.add_node("testing_tools", testing_tools_node)
# workflow.add_node("summarization_node", summarization_node)
workflow.add_node("index_project", indexer_node)
workflow.add_node("testing_node", testing_node)
# workflow.add_node("reset_testing_budget_node", reset_testing_budget_node)
workflow.add_conditional_edges(START, start_router, {
    "setup_node": "setup_node",
    "input_validation_node": "input_validation_node",
})
workflow.add_conditional_edges("planner_node", development_router, {
    "business_analyst_node": "business_analyst_node",
    "developer_node": "developer_node",
    "testing_node": "testing_node",
    "ui_ux_node": "ui_ux_node",
    "__end__": END
})
workflow.add_conditional_edges("developer_node", development_router, {
    "developer_node": "developer_node",
    "tools": "developer_tools",
    "business_analyst_node": "business_analyst_node",
    "testing_node": "testing_node",
    "ui_ux_node": "ui_ux_node",
    "__end__": END
})
workflow.add_conditional_edges("business_analyst_node", development_router, {
    "developer_node": "developer_node",
    "testing_node": "testing_node",
    "ui_ux_node": "ui_ux_node",
    "__end__": END
})
workflow.add_conditional_edges("testing_node", development_router, {
    "testing_node": "testing_node",
    "tools": "testing_tools",
    "business_analyst_node": "business_analyst_node",
    "developer_node": "developer_node",
    "ui_ux_node": "ui_ux_node",
    "__end__": END
})
workflow.add_conditional_edges("ui_ux_node", development_router, {
    "business_analyst_node": "business_analyst_node",
    "developer_node": "developer_node",
    "testing_node": "testing_node",
    "__end__": END
})
# workflow.add_conditional_edges("developer_node", tools_condition, {
#     "tools": "developer_tools",
#     "__end__": "index_project",
# })
# # Single conditional edge from testing — handles both tool dispatch and
# # back_to_developer logic to avoid the duplicate-edge error.
# workflow.add_conditional_edges("testing_node", tools_condition, {
#     "tools": "testing_tools",
#     "__end__": "index_project",
# })
# workflow.add_edge("summarization_node", "business_analyst_node")
# workflow.add_edge("business_analyst_node", "ui_ux_node")
# workflow.add_edge("ui_ux_node", "developer_node")
workflow.add_edge("developer_tools", "developer_node")
workflow.add_edge("testing_tools", "testing_node")
workflow.add_edge("setup_node", "index_project")
workflow.add_edge("input_validation_node", "planner_node")
# workflow.add_edge("reset_testing_budget_node", END)

graph = workflow.compile()
