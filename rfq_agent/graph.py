import json
from typing import Annotated

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict

from rfq_agent.tools import (
    extract_rfq_cached,
    extract_rfq_live,
    extract_rfq_structured,
    match_catalog,
)


class RFQState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    raw_lines: NotRequired[list[str]]
    domain: NotRequired[str | None]
    cache_hit: NotRequired[bool]
    structured_hit: NotRequired[bool]


def _parse_input(content: str) -> tuple[str, str | None]:
    """Return (body, domain). Input may be plain text or JSON {"body":..., "domain":...}."""
    try:
        d = json.loads(content)
        if isinstance(d, dict) and "body" in d:
            return d["body"], d.get("domain")
    except (json.JSONDecodeError, ValueError):
        pass
    return content, None


# ── nodes ─────────────────────────────────────────────────────────────────────

def extract_cached_node(state: RFQState, config: RunnableConfig) -> dict:
    body, domain = _parse_input(state["messages"][-1].content)
    result = extract_rfq_cached.invoke({"email_body": body}, config=config)
    hit = result != "null"
    return {
        "raw_lines": json.loads(result) if hit else [],
        "domain": domain,
        "cache_hit": hit,
    }


def extract_structured_node(state: RFQState, config: RunnableConfig) -> dict:
    body, _ = _parse_input(state["messages"][-1].content)
    result = extract_rfq_structured.invoke({"email_body": body}, config=config)
    hit = result != "null"
    return {
        "raw_lines": json.loads(result) if hit else [],
        "structured_hit": hit,
    }


def extract_live_node(state: RFQState, config: RunnableConfig) -> dict:
    body, _ = _parse_input(state["messages"][-1].content)
    result = extract_rfq_live.invoke({"email_body": body}, config=config)
    return {"raw_lines": json.loads(result)}


def match_node(state: RFQState, config: RunnableConfig) -> dict:
    result_str = match_catalog.invoke(
        {
            "lines_json": json.dumps(state["raw_lines"]),
            "domain": state.get("domain"),
        },
        config=config,
    )
    return {"messages": [AIMessage(content=result_str)]}


# ── routing ───────────────────────────────────────────────────────────────────

def route_after_cache(state: RFQState) -> str:
    return "match" if state["cache_hit"] else "extract_structured"


def route_after_structured(state: RFQState) -> str:
    return "match" if state["structured_hit"] else "extract_live"


# ── graph ─────────────────────────────────────────────────────────────────────

builder = StateGraph(RFQState)
builder.add_node("extract_cached", extract_cached_node)
builder.add_node("extract_structured", extract_structured_node)
builder.add_node("extract_live", extract_live_node)
builder.add_node("match", match_node)

builder.add_edge(START, "extract_cached")
builder.add_conditional_edges(
    "extract_cached",
    route_after_cache,
    {"match": "match", "extract_structured": "extract_structured"},
)
builder.add_conditional_edges(
    "extract_structured",
    route_after_structured,
    {"match": "match", "extract_live": "extract_live"},
)
builder.add_edge("extract_live", "match")
builder.add_edge("match", END)

app = builder.compile()
