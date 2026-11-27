"""De punta a punta sin gastar tokens: SDK oficial de Anthropic -> servidor falso (MockTransport).

Prueba el SDK real, el parser de eventos, la verificación, el grafo y la API SSE, contra la base
real con una guía ficticia ingestada. Se omite si no hay base.
"""
import json

import httpx2
import psycopg
import pytest
from anthropic import AsyncAnthropic
from fastapi.testclient import TestClient

from app import config
from app.embeddings import HashingEmbedder
from app.ingest.cli import ingest
from app.main import create_app
from tests.fake_anthropic import FakeAnthropic
from tests.make_fake_guide import LOSARTAN, make_fake_guide

SLUG = "test-e2e-ficticia"
QUESTION = "¿Con qué fármaco se inicia la hipertensión arterial con diabetes? losartán zz-test-e2e"
STRENGTH = "Recomendación fuerte, certeza de la evidencia moderada."


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    try:
        db = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    pdf = make_fake_guide(tmp_path_factory.mktemp("pdf") / "g.pdf")
    db.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    ingest(db, HashingEmbedder(), str(pdf), slug=SLUG, title="Guía FICTICIA de hipertensión", year=2024,
           url="https://example.org/ficticia.pdf", publisher="Ficticio")
    fake = FakeAnthropic()
    client = AsyncAnthropic(api_key="sk-test", http_client=httpx2.AsyncClient(transport=fake.transport()))
    with TestClient(create_app(embedder=HashingEmbedder(), client=client, min_similarity=0.0)) as http:
        yield http, fake
    db.execute("DELETE FROM documents WHERE slug = %s", (SLUG,))
    db.execute("DELETE FROM queries WHERE question LIKE '%zz-test-e2e%'")
    db.close()


def chat(http, fake, script, stop_reason="end_turn"):
    fake.script, fake.stop_reason = script, stop_reason
    r = http.post("/api/chat", json={"question": QUESTION})
    events = []
    for raw in r.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in raw.splitlines() if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events, events[-1][1]


def test_correct_answer_is_verified_with_page_and_paragraph(e2e):
    http, fake = e2e
    events, final = chat(http, fake, [
        ("Se recomienda iniciar losartán 50 mg al día", LOSARTAN[:40]),
        (", con recomendación fuerte.", STRENGTH),
    ])
    assert final == {"status": "verified", "message": None, "problems": []}
    tokens = "".join(d["text"] for e, d in events if e == "token")
    assert tokens == "Se recomienda iniciar losartán 50 mg al día, con recomendación fuerte."
    assert [d["block"] for e, d in events if e == "citation"] == [0, 1]
    refs = next(d for e, d in events if e == "references")
    los = next(r for r in refs if r["quote"] == LOSARTAN)
    assert los["paragraphs"] == [{"page": 1, "para": 2, "kind": "text"}]
    assert los["url"] == "https://example.org/ficticia.pdf#page=1"


def test_changed_dose_is_retracted(e2e):
    http, fake = e2e
    _, final = chat(http, fake, [("Se recomienda iniciar losartán 100 mg al día.", LOSARTAN[:40])])
    assert final["status"] == "retracted" and "100" in final["problems"][0]


def test_number_without_citation_is_retracted(e2e):
    http, fake = e2e
    _, final = chat(http, fake, [("Se recomienda iniciar losartán 50 mg al día.", LOSARTAN[:40]),
                                 (" La dosis máxima es 200 mg.", None)])
    assert final["status"] == "retracted" and "sin cita" in final["problems"][0]


def test_abstention(e2e):
    http, fake = e2e
    _, final = chat(http, fake, [("Las guías cargadas no responden esta pregunta. Cubren hipertensión.", None)])
    assert final["status"] == "abstained"


def test_truncated_answer_is_retracted(e2e):
    http, fake = e2e
    _, final = chat(http, fake, [("Se recomienda iniciar losartán 50 mg", LOSARTAN[:40])], stop_reason="max_tokens")
    assert final["status"] == "retracted"


def test_every_search_result_has_citations_enabled(e2e):
    http, fake = e2e
    chat(http, fake, [("Las guías cargadas no responden esta pregunta.", None)])
    body = fake.requests[-1]
    results = [b for b in body["messages"][0]["content"] if b["type"] == "search_result"]
    assert len(results) == config.TOP_K
    assert all(r["citations"] == {"enabled": True} for r in results)  # todos o ninguno: mezclar da error
    assert body["max_tokens"] == 4000 and body["output_config"] == {"effort": "low"}
