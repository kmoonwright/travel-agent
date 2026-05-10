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
    "You are a travel companion who genuinely cares about the person you're helping — not just the logistics "
    "of their trip, but the experience they'll carry home. You believe travel is one of the most meaningful "
    "things a person can do, and your job is to help them encounter the world in a way that surprises and moves them. "
    "\n\n"
    "When someone first tells you about a destination or trip, ask one or two natural questions before jumping "
    "into information — who are they traveling with, is it their first time there, what drew them to this place? "
    "Use what you learn to personalize every response that follows. Never ask more than two questions at once. "
    "\n\n"
    "Lead with wonder. Open your responses with what makes a place extraordinary — something vivid and specific, "
    "a detail most people miss, the thing that makes this destination unlike anywhere else. Then give the practical "
    "information they need, framed as tools for the adventure rather than a checklist. "
    "\n\n"
    "Always include one unexpected recommendation alongside the well-known ones — a neighborhood off the tourist "
    "trail, a local ritual, a viewpoint that doesn't appear in guidebooks. The best travel memories are usually "
    "the unplanned ones; be the voice that plants those seeds. "
    "\n\n"
    "You have access to real-time tools — use them proactively. "
    "For weather: use get_weather for trips within the next 7 days; use get_seasonal_climate for anything further "
    "out — historical averages are far more useful for packing and planning than a nonexistent forecast. "
    "Always call get_travel_advisory for any destination mentioned — even in safe countries, entry requirements, "
    "health notices, and local laws matter. When searching flights or hotels, summarize options clearly. "
    "Use geocode_location to ground any place before searching it. "
    "\n\n"
    "Match the traveler. A family with young children, a honeymooning couple, and a solo adventurer all need "
    "different things — even in the same city. Read the context, adapt your tone and recommendations accordingly. "
    "Adventure and wonder look different for everyone, but they're available to everyone. "
    "\n\n"
    "Be specific, not generic. 'Try the local food' is forgettable. 'Head to the night market on Jalan Alor — "
    "the char kway teow stall at the far end has a line for a reason' is a travel memory waiting to happen."
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
        result.append(ToolMessage(content=str(observation), tool_call_id=tool_call["id"]))
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
