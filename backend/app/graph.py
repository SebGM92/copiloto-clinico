"""Orquestación del flujo con LangGraph: guard -> retrieve -> generate -> verify."""
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app import acronyms, guard, llm, retrieval, verify


class State(TypedDict, total=False):
    query: str
    allowed: bool
    reason: str
    sources: list[str]
    answer: str
    grounded: bool


def guard_node(state: State) -> State:
    r = guard.check(state["query"])
    return {"allowed": r.allowed, "reason": r.reason}


def retrieve_node(state: State) -> State:
    chunks = retrieval.search(acronyms.expand(state["query"]))
    return {"sources": [c.content for c in chunks]}


def generate_node(state: State) -> State:
    return {"answer": llm.generate(state["query"], state.get("sources", []))}


def verify_node(state: State) -> State:
    r = verify.verify(state["answer"], state.get("sources", []))
    return {"grounded": r.grounded}


def build_graph():
    g = StateGraph(State)
    g.add_node("guard", guard_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_node("verify", verify_node)

    g.set_entry_point("guard")
    g.add_conditional_edges("guard", lambda s: "retrieve" if s["allowed"] else END)
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "verify")
    g.add_edge("verify", END)
    return g.compile()
