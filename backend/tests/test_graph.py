"""El grafo completo sin red: pool, embedder y cliente de Claude falsos, inyectados por closure."""
import asyncio
from types import SimpleNamespace as NS

from app.embeddings import HashingEmbedder
from app.graph import build_graph
from tests.test_llm import FakeClient, text_block

LOSARTAN = "Se recomienda iniciar losartán 50 mg al día en adultos con hipertensión arterial."


def row(similarity, keyword_rank, text=LOSARTAN, cid=1):
    return {"id": cid, "section": "1.1 Fármacos", "page_start": 4, "page_end": 4,
            "paragraphs": [{"page": 4, "para": 2, "text": text, "kind": "text"}], "content": text,
            "slug": "hta-ficticia", "title": "Guía FICTICIA de hipertensión", "year": 2024,
            "source_url": "https://x/hta.pdf", "similarity": similarity, "semantic_rank": 1,
            "keyword_rank": keyword_rank, "score": 0.03}


class FakePool:
    """Imita AsyncConnectionPool: connection() -> conexión cuyo cursor devuelve filas fijas."""

    def __init__(self, rows):
        self.rows, self.queries = rows, 0

    def connection(self):
        pool = self

        class Cursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, sql, params):
                pool.queries += 1

            async def fetchall(self):
                return pool.rows

        class Conn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def cursor(self, row_factory=None):
                return Cursor()

        return Conn()


def cited(text, cited_text=LOSARTAN):
    cite = NS(type="search_result_location", search_result_index=0, start_block_index=0, end_block_index=1,
              cited_text=cited_text)
    return text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text=text)),
                      NS(type="content_block_delta", delta=NS(type="citations_delta", citation=cite)))


def plain(text):
    return text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text=text)))


def run(question, rows, events=(), stop_reason="end_turn"):
    pool, client = FakePool(rows), FakeClient(list(events), stop_reason)
    graph = build_graph(pool, HashingEmbedder(), client, model="modelo", top_k=8, min_similarity=0.55)

    async def go():
        custom, final = [], None
        async for mode, chunk in graph.astream({"question": question}, stream_mode=["custom", "values"]):
            if mode == "custom":
                custom.append(chunk)
            else:
                final = chunk
        return final, custom

    final, custom = asyncio.run(go())
    return final, custom, pool, client


def test_question_with_run_is_blocked_before_search_and_model():
    final, custom, pool, client = run("Paciente 12.345.678-5 con HTA, ¿losartán?", [row(0.9, 1)])
    assert final["status"] == "blocked" and "RUN" in final["message"]
    assert pool.queries == 0 and client.kwargs is None and custom == []


def test_measles_question_in_hypertension_corpus_never_reaches_the_model():
    # Similitud baja y ninguna palabra en común
    final, _, _, client = run("¿Qué vacuna contra el sarampión se usa?", [row(0.21, None), row(0.18, None, cid=2)])
    assert final["status"] == "no_evidence"
    assert client.kwargs is None  # no se gastaron tokens


def test_hta_in_pregnancy_reaches_the_model_and_the_model_abstains():
    # Trampa: se parece al corpus (similitud sobre el umbral), así que llega al modelo y es él quien se abstiene
    events = plain("Las guías cargadas no responden esta pregunta. Cubren el tratamiento de la HTA en adultos.")
    final, _, _, client = run("¿Qué antihipertensivo usar en el embarazo?", [row(0.62, 1)], events)
    assert client.kwargs is not None
    assert final["status"] == "abstained"


def test_shared_common_word_alone_does_not_reach_the_model():
    # Fase 8: con la búsqueda léxica en OR, "tratamiento" coincide casi siempre; sin similitud no basta
    final, _, _, client = run("¿Cuál es el tratamiento de la tuberculosis?", [row(0.46, 1)])
    assert final["status"] == "no_evidence" and client.kwargs is None


def test_cited_answer_is_verified_and_streams_events_in_order():
    events = [*plain("La guía indica:\n- "), *cited("Losartán 50 mg al día.")]
    final, custom, _, _ = run("¿Dosis de losartán?", [row(0.72, 1)], events)
    assert final["status"] == "verified" and final["problems"] == []
    kinds = [e["event"] for e in custom]
    assert kinds[:2] == ["status", "sources"] and kinds[-1] == "references"
    assert "token" in kinds and "citation" in kinds
    assert custom[-1]["data"][0]["paragraphs"] == [{"page": 4, "para": 2, "kind": "text"}]


def test_wrong_dose_is_retracted():
    final, _, _, _ = run("¿Dosis de losartán?", [row(0.72, 1)], cited("Losartán 100 mg al día."))
    assert final["status"] == "retracted" and "100" in final["problems"][0]


def test_truncated_answer_is_retracted_even_if_well_cited():
    final, _, _, _ = run("¿Dosis de losartán?", [row(0.72, 1)], cited("Losartán 50 mg al día."), "max_tokens")
    assert final["status"] == "retracted" and "incompleta" in final["problems"][-1]
