"""stream_answer y build_search_results sin red: un cliente falso emite los eventos de streaming de la API."""
import asyncio
from types import SimpleNamespace as NS

from app.llm import EFFORT, MAX_TOKENS, AnswerBlock, Citation, build_search_results, stream_answer
from app.retrieval import RetrievedChunk

CHUNK = RetrievedChunk(
    id=1, section="3.1 PRIMERA LÍNEA > Recomendación 1", page_start=17, page_end=17,
    paragraphs=[{"page": 17, "para": 7, "text": "Se recomienda HbA1c <8%.", "kind": "text"},
                {"page": 17, "para": 8, "text": "Comentarios ficticios.", "kind": "text"}],
    content="", slug="ges-dm2-2017", title="Guía DM2", year=2017, source_url="https://x/guia.pdf",
    similarity=0.7, semantic_rank=1, keyword_rank=1, score=0.03,
)


def test_one_search_result_per_chunk_and_one_block_per_paragraph():
    (sr,) = build_search_results([CHUNK])
    assert sr["type"] == "search_result" and sr["citations"] == {"enabled": True}
    assert sr["source"] == "https://x/guia.pdf#page=17"
    assert sr["title"] == "Guía DM2 (2017) · 3.1 PRIMERA LÍNEA > Recomendación 1"
    assert [b["text"] for b in sr["content"]] == ["Se recomienda HbA1c <8%.", "Comentarios ficticios."]


class FakeStream:
    def __init__(self, events, stop_reason):
        self.events, self.stop_reason = events, stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e
        return gen()

    async def get_final_message(self):
        return NS(stop_reason=self.stop_reason)


class FakeClient:
    def __init__(self, events, stop_reason="end_turn"):
        self.kwargs = None
        self.messages = NS(stream=lambda **kw: self._stream(kw))
        self._events, self._stop = events, stop_reason

    def _stream(self, kw):
        self.kwargs = kw
        return FakeStream(self._events, self._stop)


def text_block(*deltas):
    return [NS(type="content_block_start", content_block=NS(type="text")),
            *deltas, NS(type="content_block_stop")]


def collect(client):
    async def run():
        return [x async for x in stream_answer(client, "modelo", "¿Meta de HbA1c?", [CHUNK])]
    return asyncio.run(run())


def test_blocks_citations_and_stop_reason():
    cite = NS(type="search_result_location", search_result_index=0, start_block_index=0, end_block_index=1,
              cited_text="Se recomienda HbA1c <8%.")
    events = [
        NS(type="content_block_start", content_block=NS(type="thinking")), NS(type="content_block_stop"),
        *text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text="La meta es "))),
        *text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text="HbA1c <8%.")),
                    NS(type="content_block_delta", delta=NS(type="citations_delta", citation=cite))),
    ]
    client = FakeClient(events)
    out = collect(client)
    blocks = [v for k, v in out if k == "block_end"]
    assert blocks == [AnswerBlock("La meta es ", []),
                      AnswerBlock("HbA1c <8%.", [Citation(0, 0, 1, "Se recomienda HbA1c <8%.")])]
    assert out[-1] == ("stop", "end_turn")  # el bloque de razonamiento (thinking) no genera block_end
    assert client.kwargs["max_tokens"] == MAX_TOKENS and client.kwargs["output_config"] == {"effort": EFFORT}


def test_truncated_answer_reports_max_tokens():
    out = collect(FakeClient(text_block(NS(type="content_block_delta", delta=NS(type="text_delta", text="La met"))),
                             stop_reason="max_tokens"))
    assert out[-1] == ("stop", "max_tokens")
