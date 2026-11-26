"""Ingesta de una guía clínica: PDF -> párrafos -> fragmentos -> embeddings -> PostgreSQL.

Uso:
    python -m app.ingest.cli data/guides/dm2_minsal.pdf --slug ges-dm2-2017 \\
        --title "Guía de Práctica Clínica Tratamiento Farmacológico de la Diabetes Mellitus tipo 2" \\
        --year 2017 --url https://...
"""
import argparse
import hashlib
from dataclasses import asdict

import psycopg
from psycopg.types.json import Jsonb

from app import config
from app.embeddings import BgeM3Embedder, Embedder, HashingEmbedder
from app.ingest.chunker import chunk_paragraphs
from app.ingest.pdf_parser import parse_pdf


def embedding_text(title: str, section: str, content: str) -> str:
    # El título y la sección dan contexto a un párrafo que solo dice "se recomienda iniciar con..."
    return f"{title}\n{section}\n\n{content}"


def ingest(conn: psycopg.Connection, embedder: Embedder, path: str, *, slug: str, title: str,
           year: int, url: str, publisher: str = "MINSAL") -> int:
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    existing = conn.execute("SELECT id, sha256 FROM documents WHERE slug = %s", (slug,)).fetchone()
    if existing and existing[1] == sha:
        print(f"{slug}: sin cambios, se omite")
        return existing[0]

    chunks = chunk_paragraphs(parse_pdf(path))
    vectors = embedder.embed([embedding_text(title, c.section, c.text) for c in chunks])

    with conn.transaction():
        conn.execute("DELETE FROM documents WHERE slug = %s", (slug,))  # borra también sus chunks
        doc_id = conn.execute(
            """INSERT INTO documents (slug, title, publisher, year, source_url, sha256)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (slug, title, publisher, year, url, sha),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (document_id, ordinal, section, page_start, page_end, paragraphs, content, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (doc_id, i, c.section, c.page_start, c.page_end,
                     Jsonb([asdict(p) for p in c.paragraphs]), c.text, vec)
                    for i, (c, vec) in enumerate(zip(chunks, vectors))
                ],
            )
    print(f"{slug}: {len(chunks)} fragmentos")
    return doc_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de una guía clínica en PDF")
    parser.add_argument("path", help="ruta al PDF")
    parser.add_argument("--slug", required=True, help="identificador estable, ej: ges-dm2-2017")
    parser.add_argument("--title", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--url", required=True, help="URL del PDF original")
    parser.add_argument("--publisher", default="MINSAL")
    parser.add_argument("--fake-embedder", action="store_true",
                        help="usa el embedder de hashing (sin modelo, solo para pruebas)")
    args = parser.parse_args()

    embedder = HashingEmbedder() if args.fake_embedder else BgeM3Embedder(config.EMBEDDING_MODEL)
    # autocommit: conn.transaction() abre una transacción real, no un savepoint dentro de otra
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        ingest(conn, embedder, args.path, slug=args.slug, title=args.title, year=args.year,
               url=args.url, publisher=args.publisher)


if __name__ == "__main__":
    main()
