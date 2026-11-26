"""Búsqueda de fragmentos relevantes en pgvector."""
from dataclasses import dataclass

from app import config


@dataclass
class Chunk:
    id: int
    document_id: int
    page: int | None
    content: str
    score: float


def search(query: str, k: int | None = None) -> list[Chunk]:
    # TODO: embed(query) + similitud coseno en chunks; k = k or config.TOP_K,
    #       descartar resultados con score < config.MIN_SIMILARITY
    raise NotImplementedError
