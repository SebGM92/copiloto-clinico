"""API FastAPI del copiloto clínico."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.graph import build_graph

app = FastAPI(title="Copiloto Clínico")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
graph = build_graph()


class AskRequest(BaseModel):
    query: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    return graph.invoke({"query": req.query})
