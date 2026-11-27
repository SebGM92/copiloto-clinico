"""Compara búsqueda solo semántica, solo léxica e híbrida con las preguntas de eval/questions.json.

Acierto: algún fragmento de la guía correcta, entre los primeros N, cubre una de las páginas correctas.
Uso (desde backend/, con el .env cargado):
    python -m eval.retrieval_modes
"""
import asyncio
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app import config
from app.acronyms import expand
from app.embeddings import BgeM3Embedder
from app.retrieval import CANDIDATES, HYBRID_SQL

QUESTIONS = Path(__file__).resolve().parent / "questions.json"
TOP = 8
WIDE = 20  # para decidir si hace falta reranking: ¿está entre los 20 pero no entre los 8?

SEMANTIC_SQL = """
SELECT c.page_start, c.page_end, d.slug FROM chunks c JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> %(vec)s::vector LIMIT %(k)s
"""
KEYWORD_SQL = """
WITH q AS (SELECT replace(plainto_tsquery('es_med', %(text)s)::text, ' & ', ' | ')::tsquery AS query)
SELECT c.page_start, c.page_end, d.slug FROM chunks c JOIN documents d ON d.id = c.document_id, q
WHERE q.query::text <> '' AND c.tsv @@ q.query
ORDER BY ts_rank_cd(c.tsv, q.query) DESC LIMIT %(k)s
"""


def first_hit(rows: list[dict], slug: str, gold: list[int]) -> int | None:
    """Posición (1-based) del primer fragmento que cubre una página correcta."""
    for i, r in enumerate(rows, start=1):
        if r["slug"] == slug and any(r["page_start"] <= p <= r["page_end"] for p in gold):
            return i
    return None


async def main() -> None:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    embedder = BgeM3Embedder(config.EMBEDDING_MODEL)
    vectors = embedder.embed([q["question"] for q in questions])
    modes = {"semántica": SEMANTIC_SQL, "léxica": KEYWORD_SQL, "híbrida": HYBRID_SQL}
    results: dict[str, list[int | None]] = {m: [] for m in modes}

    async with await psycopg.AsyncConnection.connect(config.DATABASE_URL) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            for q, vec in zip(questions, vectors):
                params = {"text": expand(q["question"]), "vec": vec, "k": max(WIDE, CANDIDATES)}
                for mode, sql in modes.items():
                    await cur.execute(sql, params)
                    results[mode].append(first_hit((await cur.fetchall())[:WIDE], q["slug"], q["gold_pages"]))

    n = len(questions)
    print(f"| Búsqueda | Página correcta en top {TOP} | En top {WIDE} pero no en top {TOP} |")
    print("|---|---|---|")
    for mode, pos in results.items():
        top = sum(p is not None and p <= TOP for p in pos)
        wide = sum(p is not None and TOP < p <= WIDE for p in pos)
        print(f"| {mode} | {top}/{n} ({top / n:.0%}) | {wide} |")
    print("\nPosición de la primera página correcta (— = fuera del top 20):")
    print("| Pregunta | " + " | ".join(modes) + " |")
    print("|---|" + "---|" * len(modes))
    for i, q in enumerate(questions):
        cells = [str(results[m][i]) if results[m][i] else "—" for m in modes]
        print(f"| {q['id']} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    asyncio.run(main())
