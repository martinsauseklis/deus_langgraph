import inspect

import anthropic
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END
from agent.utils.state import AgentState
from agent.utils.model_config import MODEL_NAME
from langchain_core.runnables import RunnableConfig
from agent.utils.logger import add_logger, logger
from agent.utils.nodes.business_analyst_node.tools_node import business_analyst_tools
import asyncio


sonnet = ChatAnthropic(
    model_name=MODEL_NAME,
    streaming=True,
    max_retries=2,
)


@add_logger
async def business_analyst_node(
    state: AgentState, config: RunnableConfig
) -> AgentState:

    sonnet_with_tools = sonnet.bind_tools(business_analyst_tools)

    agent_input = [
        SystemMessage("""You are a business analyst that translates customers' needs
                    into specific technical tasks to be passed to the UI/UX engineer.
                    Keep in mind that we are working currently on an existing Next.js
                    project. Don't assume anything else or offer to work on anything else.
                    Senior developer will have a context of the app structure, so you don't need to explain
                    the Next.js part. 
                    Before you start, ask user the 5 most important questions that would help you do this well. 
                    After user answers, then begin.
                    
                    You are also coherent plan developer by combining the outputs of other agents that you can invoke. When plan is set, 
                    all info from user is gathered, ask user if you can proceed with building and then again - call agents in sequence so they
                    can do their job of creating the project.
                    Do the development in iterative way - build outline so user can immediately check and when one development cycle is done then start focusing
                    more on details. Just so you don't overengineer and build something that was not needed for the user. It is important to keep this in mind
                    also for agents you are going to call - be specific about the iterations and don't let them to go into too many details when it is not 
                    yet necessary."""),
        *state["messages"],
    ]

    # if state["messages"][-1].type == "ai":
    #     agent_input.append(HumanMessage("The task result of the agent you had called is in the previous message."))

    try:
        # response = await sonnet_with_output.astream_events(input=agent_input)
        response = await sonnet_with_tools.ainvoke(input=agent_input, config=config) 
        response.name = "business_analyst"

        return {
            "messages": [response],
            "ba_tool_calls": len(response.tool_calls),
            "testing_tool_call_count": 0,
            "tool_call_count": 0,
        }

    except anthropic.APIError as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with Anthropic API error: {e.message}"
                )
            ]
        }

    except Exception as e:
        return {
            "messages": [
                AIMessage(
                    f"Node {inspect.currentframe().f_code.co_name} failed with: {str(e)}"
                )
            ]
        }
