"""Servidor falso de la API de Anthropic para el SDK oficial (httpx2.MockTransport).

Responde POST /v1/messages en el mismo formato SSE que la API real. Cada test fija un guion:
una lista de segmentos (texto, frase_a_citar). Si hay frase, el servidor busca en qué search_result
y en qué bloque (párrafo) aparece, y arma la cita con el bloque completo, como lo hace Claude.
"""
import json

import httpx2


class FakeAnthropic:
    def __init__(self):
        self.script: list[tuple[str, str | None]] = []
        self.stop_reason = "end_turn"
        self.requests: list[dict] = []

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handle)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/messages", request.url.path
        body = json.loads(request.content)
        self.requests.append(body)
        results = [b for m in body["messages"] for b in m["content"]
                   if isinstance(b, dict) and b.get("type") == "search_result"]
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=self._sse(body["model"], results).encode())

    def _locate(self, results, phrase):
        for i, r in enumerate(results):
            for j, block in enumerate(r["content"]):
                if phrase in block["text"]:
                    return i, j, r, block["text"]
        raise AssertionError(f"El servidor falso no encontró «{phrase}» en los search_result recibidos")

    def _sse(self, model, results) -> str:
        events = [("message_start", {"type": "message_start", "message": {
            "id": "msg_fake", "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 0}}})]
        for index, (text, phrase) in enumerate(self.script):
            events.append(("content_block_start", {"type": "content_block_start", "index": index,
                                                   "content_block": {"type": "text", "text": "", "citations": []}}))
            if phrase:
                i, j, result, block_text = self._locate(results, phrase)
                events.append(("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {
                    "type": "citations_delta", "citation": {
                        "type": "search_result_location", "cited_text": block_text, "search_result_index": i,
                        "source": result["source"], "title": result["title"],
                        "start_block_index": j, "end_block_index": j + 1}}}))
            events.append(("content_block_delta", {"type": "content_block_delta", "index": index,
                                                   "delta": {"type": "text_delta", "text": text}}))
            events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
        events.append(("message_delta", {"type": "message_delta",
                                         "delta": {"stop_reason": self.stop_reason, "stop_sequence": None},
                                         "usage": {"output_tokens": 50}}))
        events.append(("message_stop", {"type": "message_stop"}))
        return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
