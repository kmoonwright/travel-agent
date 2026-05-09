import operator
import sys
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from tools import ALL_TOOLS  # noqa: E402

tools = ALL_TOOLS
tools_by_name = {tool.name: tool for tool in tools}

model = ChatOpenAI(model="gpt-4o", temperature=0)
model_with_tools = model.bind_tools(tools)

SYSTEM_PROMPT = (
    "You are an expert travel assistant with access to real-time tools for planning trips. "
    "You can look up weather forecasts, find tourist attractions and restaurants, check live "
    "currency exchange rates, search for flights and hotels, retrieve travel safety advisories, "
    "check local times at destinations, and calculate trip durations. "
    "Use tools proactively to give accurate, up-to-date information rather than relying on general knowledge. "
    "For weather: use get_weather for current conditions or trips within the next 7 days. "
    "For trips more than a week away, use get_seasonal_climate with the travel month to provide "
    "historical averages — this is far more useful for packing and planning than a forecast that doesn't exist yet. "
    "Always call get_travel_advisory for any destination a traveler mentions, regardless of safety level — "
    "even safe countries have entry requirements, health notices, and local laws worth knowing. "
    "When searching for flights or hotels, clearly summarize the key options. "
    "Be helpful, specific, and practical — travelers need actionable information."
)


class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]


def llm_call(state: MessagesState) -> dict:
    """Call the LLM with the current messages and available tools."""
    return {
        "messages": [
            model_with_tools.invoke(
                [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
            )
        ]
    }


def tool_node(state: MessagesState) -> dict:
    """Execute tool calls from the last message."""
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


def should_continue(state: MessagesState) -> Literal["tool_node", "__end__"]:
    """Determine whether to continue to tool execution or end."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool_node"
    return END


def build_agent():
    graph_builder = StateGraph(MessagesState)

    graph_builder.add_node("llm_call", llm_call)
    graph_builder.add_node("tool_node", tool_node)

    graph_builder.add_edge(START, "llm_call")
    graph_builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph_builder.add_edge("tool_node", "llm_call")

    return graph_builder.compile()
