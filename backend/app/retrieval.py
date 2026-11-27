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


def search(question: str, k: int | None = None) -> list[Chunk]:
    """Búsqueda híbrida.

    - Semántica: embedding de la pregunta ORIGINAL.
    - Léxica: tsquery de la pregunta ampliada con acronyms.expand().
    Si la evaluación muestra que una sigla también confunde a la búsqueda semántica,
    se amplía ahí también y se mide la diferencia.
    """
    # TODO: consulta SQL híbrida con RRF; k = k or config.TOP_K,
    #       descartar resultados con score < config.MIN_SIMILARITY
    raise NotImplementedError
