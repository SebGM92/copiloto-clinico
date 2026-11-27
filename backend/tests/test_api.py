"""La API completa contra la base real, con embedder de hashing y un Claude falso. Se omite si no hay base."""
import json
from types import SimpleNamespace as NS

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.embeddings import HashingEmbedder
from app.main import create_app
from tests.test_llm import FakeStream, text_block

MARK = "zz-test-api"  # para encontrar y borrar las filas de queries que crean estos tests


class CitingClient:
    """Claude falso: cita el primer párrafo del primer search_result que recibe, copiándolo tal cual."""

    def __init__(self):
        self.calls = 0
        self.messages = NS(stream=self._stream)

    def _stream(self, **kw):
        self.calls += 1
        first = kw["messages"][0]["content"][0]["content"][0]["text"]
        cite = NS(type="search_result_location", search_result_index=0, start_block_index=0, end_block_index=1,
                  cited_text=first)
        events = [*text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text="Según la guía:\n- "))),
                  *text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text=first)),
                              NS(type="content_block_delta", delta=NS(type="citations_delta", citation=cite)))]
        return FakeStream(events, "end_turn")


@pytest.fixture(scope="module")
def api():
    try:
        db = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    client = CitingClient()
    with TestClient(create_app(embedder=HashingEmbedder(), client=client, min_similarity=0.0)) as http:
        yield http, client, db
    db.execute("DELETE FROM queries WHERE question LIKE %s OR answer LIKE %s", (f"%{MARK}%", f"%{MARK}%"))
    db.execute("DELETE FROM queries WHERE question = '[bloqueada: contenía datos de paciente]' "
               "AND at > now() - interval '5 minutes'")
    db.close()


def sse(response) -> list[tuple[str, object]]:
    events = []
    for raw in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in raw.splitlines() if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def last_query(db):
    return db.execute("SELECT question, status, answer, chunk_ids, problems, latency_ms FROM queries "
                      "ORDER BY id DESC LIMIT 1").fetchone()


def test_documents_lists_guides_with_chunk_counts(api):
    http, _, _ = api
    docs = http.get("/api/documents").json()
    assert docs and all({"slug", "title", "year", "source_url", "chunks"} <= d.keys() for d in docs)


def test_chat_streams_stages_answer_and_verdict_and_logs_the_query(api):
    http, client, db = api
    r = http.post("/api/chat", json={"question": f"¿Meta de HbA1c en adultos mayores frágiles? {MARK}"})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = sse(r)
    kinds = [e for e, _ in events]
    assert kinds[0] == "status" and kinds[1] == "sources" and kinds[-1] == "final"
    assert {"token", "citation", "references"} <= set(kinds)
    assert [d["stage"] for e, d in events if e == "status"] == ["buscando", "generando", "verificando"]
    final = events[-1][1]
    assert final["status"] == "verified" and final["problems"] == []

    question, status, answer, chunk_ids, problems, latency = last_query(db)
    assert MARK in question and status == "verified" and answer.startswith("Según la guía")
    assert len(chunk_ids) == config.TOP_K and problems == [] and latency >= 0


def test_blocked_question_never_reaches_the_model_and_the_run_is_not_logged(api):
    http, client, db = api
    calls = client.calls
    events = sse(http.post("/api/chat", json={"question": "Paciente 12.345.678-5, ¿inicio insulina?"}))
    assert events == [("final", {"status": "blocked", "message": events[0][1]["message"], "problems": []})]
    assert client.calls == calls
    question, status, *_ = last_query(db)
    assert status == "blocked" and "12.345.678" not in question


def test_rate_limit_per_ip_answers_429_without_reaching_the_model():
    try:
        psycopg.connect(config.DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    client = CitingClient()
    app = create_app(embedder=HashingEmbedder(), client=client, min_similarity=0.0, rate_limit=(2, 600))
    with TestClient(app) as http:
        codes = [http.post("/api/chat", json={"question": "Paciente 12.345.678-5"}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        r = http.post("/api/chat", json={"question": f"¿Dosis de losartán? {MARK}"})
        assert r.status_code == 429 and "Demasiadas preguntas" in r.json()["detail"]
    assert client.calls == 0


def test_question_validation(api):
    http, _, _ = api
    assert http.post("/api/chat", json={"question": "hi"}).status_code == 422
    assert http.post("/api/chat", json={"question": "x" * 2001}).status_code == 422
