"""Búsqueda híbrida contra la base real (docker compose up -d db). Se omite si no hay base."""
import asyncio

import psycopg
import pytest

from app import config
from app.embeddings import HashingEmbedder
from app.ingest.cli import ingest
from app.retrieval import CANDIDATES, hybrid_search
from tests.make_fake_guide import LOSARTAN, make_fake_guide

SLUG = "test-retrieval-ficticia"


@pytest.fixture
def fake_guide(tmp_path):
    try:
        conn = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    conn.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    ingest(conn, HashingEmbedder(), str(make_fake_guide(tmp_path / "g.pdf")), slug=SLUG,
           title="Guía FICTICIA de hipertensión", year=2024, url="https://example.org/f.pdf", publisher="Ficticio")
    yield conn
    conn.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    conn.close()


def search(question, vector, k=8):
    async def run():
        async with await psycopg.AsyncConnection.connect(config.DATABASE_URL) as conn:
            return await hybrid_search(conn, question, vector, k=k)
    return asyncio.run(run())


def losartan_hit(results):
    return next((r for r in results if r.slug == SLUG and LOSARTAN in r.content), None)


def test_semantic_and_keyword_hit_returns_citable_chunk(fake_guide):
    q = "¿Se recomienda losartán en hipertensión arterial con diabetes?"
    hit = losartan_hit(search(q, HashingEmbedder().embed([LOSARTAN])[0]))
    assert hit is not None
    assert hit.semantic_rank is not None and hit.keyword_rank is not None
    assert hit.title == "Guía FICTICIA de hipertensión" and hit.year == 2024
    los = next(p for p in hit.paragraphs if p["text"] == LOSARTAN)
    assert (los["page"], los["para"]) == (1, 2)  # la cita sale de la búsqueda, sin abrir el PDF


def test_keyword_only_hit_enters_the_ranking(fake_guide):
    # Vector opuesto al del fragmento de losartán: queda último en la búsqueda semántica (fuera de
    # los CANDIDATES), pero la léxica lo encuentra. FULL OUTER JOIN: entra igual, con semantic_rank nulo.
    total = fake_guide.execute("SELECT count(*) FROM chunks").fetchone()[0]
    ours = fake_guide.execute(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.slug = %s", (SLUG,)
    ).fetchone()[0]
    if total - ours < CANDIDATES:
        pytest.skip("hacen falta más fragmentos en la base (ingesta las guías reales)")
    vector = [-x for x in HashingEmbedder().embed([LOSARTAN])[0]]
    hit = losartan_hit(search("losartán", vector))
    assert hit is not None
    assert hit.semantic_rank is None and hit.keyword_rank is not None and hit.similarity is None


def test_or_semantics_tolerates_words_absent_from_the_corpus(fake_guide):
    # Con AND (plainto_tsquery sin reemplazo) "zzzinexistente" haría que no se encontrara nada
    vector = HashingEmbedder().embed(["zzzinexistente"])[0]
    hit = losartan_hit(search("losartán zzzinexistente", vector))
    assert hit is not None and hit.keyword_rank is not None


def test_acronym_expansion_feeds_the_keyword_search(fake_guide):
    # "HTA" no aparece en la guía ficticia; "hipertensión arterial" sí, gracias a expand()
    other = HashingEmbedder().embed(["zzzinexistente"])[0]
    results = search("HTA", other, k=40)
    assert any(r.slug == SLUG and r.keyword_rank is not None and "hipertensión arterial" in r.content
               for r in results)
