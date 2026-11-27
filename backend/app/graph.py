"""Flujo del copiloto en LangGraph: guard -> retrieve -> evidencia -> generate -> verify."""
import asyncio
from dataclasses import asdict
from typing import TypedDict

from anthropic import AsyncAnthropic
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from psycopg_pool import AsyncConnectionPool

from . import config
from .embeddings import Embedder
from .guard import find_patient_data
from .llm import AnswerBlock, stream_answer
from .retrieval import RetrievedChunk, hybrid_search
from .verify import verify


class State(TypedDict, total=False):
    question: str
    chunks: list[RetrievedChunk]
    blocks: list[AnswerBlock]
    stop_reason: str     # "end_turn" si la respuesta llegó completa
    status: str          # blocked | no_evidence | verified | retracted | abstained
    message: str
    problems: list[str]


def build_graph(pool: AsyncConnectionPool, embedder: Embedder, client: AsyncAnthropic,
                model: str = config.ANTHROPIC_MODEL, top_k: int = config.TOP_K,
                min_similarity: float = config.MIN_SIMILARITY):

    async def guard(state: State) -> State:
        reason = find_patient_data(state["question"])
        if reason:
            return {"status": "blocked", "message": reason}
        return {}

    async def retrieve(state: State) -> State:
        write = get_stream_writer()
        write({"event": "status", "data": {"stage": "buscando"}})
        vector = (await asyncio.to_thread(embedder.embed, [state["question"]]))[0]
        async with pool.connection() as conn:
            chunks = await hybrid_search(conn, state["question"], vector, k=top_k)
        write({"event": "sources", "data": [
            {"n": i + 1, "title": c.title, "year": c.year, "section": c.section,
             "page_start": c.page_start, "page_end": c.page_end, "url": f"{c.source_url}#page={c.page_start}"}
            for i, c in enumerate(chunks)
        ]})
        return {"chunks": chunks}

    async def check_evidence(state: State) -> State:
        chunks = state["chunks"]
        best = max((c.similarity or 0 for c in chunks), default=0)
        # Solo similitud: con la búsqueda léxica en OR, casi cualquier pregunta comparte alguna palabra
        # ("tratamiento", "niños") y el chequeo no bloqueaba nada. Calibrado en la Fase 8 (ver README).
        if not chunks or best < min_similarity:
            return {"status": "no_evidence",
                    "message": "No encontré evidencia suficiente en las guías cargadas para responder."}
        return {}

    async def generate(state: State) -> State:
        write = get_stream_writer()
        write({"event": "status", "data": {"stage": "generando"}})
        blocks: list[AnswerBlock] = []
        stop_reason = None
        async for kind, payload in stream_answer(client, model, state["question"], state["chunks"]):
            if kind == "text":
                write({"event": "token", "data": {"text": payload, "block": len(blocks)}})
            elif kind == "citation":
                write({"event": "citation", "data": {"block": len(blocks), "n": payload.search_result_index + 1}})
            elif kind == "block_end":
                blocks.append(payload)
            elif kind == "stop":
                stop_reason = payload
        return {"blocks": blocks, "stop_reason": stop_reason}

    async def check_answer(state: State) -> State:
        write = get_stream_writer()
        write({"event": "status", "data": {"stage": "verificando"}})
        result = verify(state["blocks"], state["chunks"])
        status, problems = result.status, list(result.problems)
        if state.get("stop_reason") != "end_turn":
            # Cortada por max_tokens o rechazada: aunque lo escrito esté bien citado, está incompleta
            status = "retracted"
            problems.append(f"La respuesta quedó incompleta (stop_reason: {state.get('stop_reason')})")
        write({"event": "references", "data": [asdict(r) for r in result.refs]})
        return {"status": status, "problems": problems}

    def after_guard(state: State) -> str:
        return END if state.get("status") == "blocked" else "retrieve"

    def after_evidence(state: State) -> str:
        return END if state.get("status") == "no_evidence" else "generate"

    graph = StateGraph(State)
    graph.add_node("guard", guard)
    graph.add_node("retrieve", retrieve)
    graph.add_node("check_evidence", check_evidence)
    graph.add_node("generate", generate)
    graph.add_node("verify", check_answer)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard, ["retrieve", END])
    graph.add_edge("retrieve", "check_evidence")
    graph.add_conditional_edges("check_evidence", after_evidence, ["generate", END])
    graph.add_edge("generate", "verify")
    graph.add_edge("verify", END)
    return graph.compile()
