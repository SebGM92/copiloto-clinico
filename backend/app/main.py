"""API FastAPI del copiloto clínico."""
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from app import config
from app.embeddings import BgeM3Embedder
from app.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Las dependencias se crean una vez al iniciar: bge-m3 tarda ~10 s en cargar
    async with AsyncConnectionPool(config.DATABASE_URL, open=False) as pool:
        app.state.graph = build_graph(pool, BgeM3Embedder(config.EMBEDDING_MODEL), AsyncAnthropic())
        yield


app = FastAPI(title="Copiloto Clínico", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
async def ask(req: AskRequest) -> dict:
    # Provisorio: sin streaming. Devuelve el estado final del grafo.
    state = await app.state.graph.ainvoke({"question": req.question})
    return {"status": state["status"], "message": state.get("message"),
            "answer": "".join(b.text for b in state.get("blocks", [])), "problems": state.get("problems", [])}
