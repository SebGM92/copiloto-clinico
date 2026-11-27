"""Búsqueda híbrida: semántica (pgvector) + léxica (tsvector), fusionadas con RRF en una sola consulta.

El embedding usa la pregunta ORIGINAL; la ampliación de siglas (acronyms.expand) solo alimenta
la búsqueda léxica. Si la evaluación muestra que una sigla también confunde a la búsqueda
semántica, se amplía ahí también y se mide la diferencia.
"""
from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .acronyms import expand

# Reciprocal Rank Fusion: cada lista aporta 1 / (RRF_K + posición).
# 60 es el valor del paper original y funciona bien sin ajuste.
RRF_K = 60
CANDIDATES = 40  # cuántos resultados trae cada búsqueda antes de fusionar

HYBRID_SQL = f"""
WITH q AS (
    -- OR entre términos: una pregunta en lenguaje natural casi nunca contiene TODAS las palabras
    SELECT replace(plainto_tsquery('es_med', %(text)s)::text, ' & ', ' | ')::tsquery AS query
),
semantic AS (
    SELECT id, 1 - (embedding <=> %(vec)s::vector) AS similarity,
           row_number() OVER (ORDER BY embedding <=> %(vec)s::vector) AS rank
    FROM chunks
    ORDER BY embedding <=> %(vec)s::vector
    LIMIT {CANDIDATES}
),
keyword AS (
    SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.query) DESC) AS rank
    FROM chunks c, q
    WHERE q.query::text <> '' AND c.tsv @@ q.query
    ORDER BY ts_rank_cd(c.tsv, q.query) DESC
    LIMIT {CANDIDATES}
)
SELECT c.id, c.section, c.page_start, c.page_end, c.paragraphs, c.content,
       d.slug, d.title, d.year, d.source_url,
       s.similarity, s.rank AS semantic_rank, k.rank AS keyword_rank,
       COALESCE(1.0 / ({RRF_K} + s.rank), 0) + COALESCE(1.0 / ({RRF_K} + k.rank), 0) AS score
FROM semantic s
FULL OUTER JOIN keyword k ON k.id = s.id
JOIN chunks c ON c.id = COALESCE(s.id, k.id)
JOIN documents d ON d.id = c.document_id
ORDER BY score DESC
LIMIT %(k)s
"""


@dataclass
class RetrievedChunk:
    id: int
    section: str
    page_start: int
    page_end: int
    paragraphs: list[dict]
    content: str
    slug: str
    title: str
    year: int
    source_url: str
    similarity: float | None
    semantic_rank: int | None
    keyword_rank: int | None
    score: float


async def hybrid_search(conn: AsyncConnection, question: str, query_vector: list[float], k: int = 8) -> list[RetrievedChunk]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(HYBRID_SQL, {"text": expand(question), "vec": query_vector, "k": k})
        rows = await cur.fetchall()
    return [RetrievedChunk(**row) for row in rows]
