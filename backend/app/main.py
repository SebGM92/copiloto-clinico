import time
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pgvector.psycopg import register_vector_async
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from . import config
from .embeddings import BgeM3Embedder
from .graph import build_graph


async def _configure(conn):
    await register_vector_async(conn)


def create_app(embedder=None, client=None) -> FastAPI:
    """Fábrica de la app: los tests inyectan un embedder y un cliente de Anthropic falsos."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pool = AsyncConnectionPool(config.DATABASE_URL, configure=_configure, open=False)
        await app.state.pool.open()
        app.state.graph = build_graph(
            app.state.pool,
            embedder or BgeM3Embedder(config.EMBEDDING_MODEL),
            client or AsyncAnthropic(),  # lee ANTHROPIC_API_KEY del entorno
        )
        yield
        await app.state.pool.close()

    app = FastAPI(title="Copiloto clínico", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

    class Question(BaseModel):
        question: str = Field(min_length=3, max_length=2000)

    @app.get("/api/documents")
    async def documents(request: Request):
        async with request.app.state.pool.connection() as conn:
            cur = await conn.execute(
                """SELECT d.slug, d.title, d.publisher, d.year, d.source_url, count(c.id) AS chunks
                   FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                   GROUP BY d.id ORDER BY d.title"""
            )
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in await cur.fetchall()]

    @app.post("/api/chat", response_class=EventSourceResponse)
    async def chat(body: Question, request: Request):
        started = time.monotonic()
        final: dict = {}
        async for mode, payload in request.app.state.graph.astream(
            {"question": body.question}, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield ServerSentEvent(event=payload["event"], data=payload["data"])
            else:
                final = payload  # el último "values" es el estado final del grafo

        answer = "".join(b.text for b in final.get("blocks", []))
        # Una pregunta bloqueada puede traer un RUN: nunca se guarda tal cual
        logged_question = "[bloqueada: contenía datos de paciente]" if final.get("status") == "blocked" else body.question
        yield ServerSentEvent(event="final", data={
            "status": final.get("status"),
            "message": final.get("message"),
            "problems": final.get("problems", []),
        })
        async with request.app.state.pool.connection() as conn:
            await conn.execute(
                """INSERT INTO queries (question, status, answer, chunk_ids, problems, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (logged_question, final.get("status"), answer,
                 [c.id for c in final.get("chunks", [])], Jsonb(final.get("problems", [])),
                 int((time.monotonic() - started) * 1000)),
            )

    return app


app = create_app()
