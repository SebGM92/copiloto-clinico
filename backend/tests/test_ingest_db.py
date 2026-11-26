"""Ingesta contra la base real (docker compose up -d db). Se omite si no hay base."""
import psycopg
import pytest

from app import config
from app.embeddings import HashingEmbedder
from app.ingest.cli import embedding_text, ingest
from tests.make_fake_guide import LOSARTAN, make_fake_guide

SLUG = "test-guia-ficticia"


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    c.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    yield c
    c.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    c.close()


def run(conn, path):
    return ingest(conn, HashingEmbedder(), str(path), slug=SLUG, title="Guía FICTICIA de hipertensión",
                  year=2024, url="https://example.org/ficticia.pdf", publisher="Ficticio")


def test_embedding_text_includes_title_and_section():
    assert embedding_text("Guía DM2", "3. Recomendaciones", "Se recomienda iniciar con...") == (
        "Guía DM2\n3. Recomendaciones\n\nSe recomienda iniciar con...")


def test_ingest_stores_chunks_with_citable_paragraphs(conn, tmp_path):
    doc_id = run(conn, make_fake_guide(tmp_path / "g.pdf"))
    n, ordinals = conn.execute(
        "SELECT count(*), array_agg(ordinal ORDER BY ordinal) FROM chunks WHERE document_id = %s", (doc_id,)
    ).fetchone()
    assert n > 0 and ordinals == list(range(n))

    section, paragraphs, content = conn.execute(
        "SELECT section, paragraphs, content FROM chunks WHERE document_id = %s AND content LIKE %s",
        (doc_id, "%losartán 50 mg%"),
    ).fetchone()
    assert section == "1. Tratamiento farmacológico > 1.1 Fármacos de primera línea"
    los = next(p for p in paragraphs if p["text"] == LOSARTAN)
    assert (los["page"], los["para"], los["kind"]) == (1, 2, "text")  # la cita sale del JSONB, sin abrir el PDF
    assert "Recomendación fuerte" in content


def test_reingest_same_pdf_is_skipped(conn, tmp_path, capsys):
    pdf = make_fake_guide(tmp_path / "g.pdf")
    first = run(conn, pdf)
    ids_before = conn.execute("SELECT array_agg(id ORDER BY id) FROM chunks WHERE document_id = %s", (first,)).fetchone()[0]
    assert run(conn, pdf) == first
    assert "sin cambios" in capsys.readouterr().out
    ids_after = conn.execute("SELECT array_agg(id ORDER BY id) FROM chunks WHERE document_id = %s", (first,)).fetchone()[0]
    assert ids_after == ids_before


def test_changed_pdf_replaces_everything(conn, tmp_path):
    pdf = make_fake_guide(tmp_path / "g.pdf")
    first = run(conn, pdf)
    pdf.write_bytes(pdf.read_bytes() + b"\n% cambio\n")  # mismo contenido, distinto hash
    second = run(conn, pdf)
    assert second != first
    docs = conn.execute("SELECT count(*) FROM documents WHERE slug = %s", (SLUG,)).fetchone()[0]
    orphans = conn.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (first,)).fetchone()[0]
    assert (docs, orphans) == (1, 0)  # nunca quedan fragmentos de dos versiones


def test_failed_ingest_leaves_previous_version_intact(conn, tmp_path):
    pdf = make_fake_guide(tmp_path / "g.pdf")
    first = run(conn, pdf)
    n_before = conn.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (first,)).fetchone()[0]

    class Broken(HashingEmbedder):
        def embed(self, texts):
            return [v[:10] for v in super().embed(texts)]  # dimensión equivocada: el INSERT falla

    pdf.write_bytes(pdf.read_bytes() + b"\n% cambio\n")
    with pytest.raises(psycopg.Error):
        ingest(conn, Broken(), str(pdf), slug=SLUG, title="t", year=2024, url="u")
    n_after = conn.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (first,)).fetchone()[0]
    assert n_after == n_before  # la transacción se revirtió: sigue la versión anterior completa
