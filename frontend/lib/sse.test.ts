// Corre con el runner de Node, sin dependencias: `npm test`
import assert from "node:assert/strict";
import { test } from "node:test";

import { readSSE, type SSEEvent } from "./sse.ts";

/** Una Response cuyo cuerpo llega en los trozos dados, como por la red. */
function responseFrom(chunks: (string | Uint8Array)[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? encoder.encode(c) : c);
      controller.close();
    },
  });
  return new Response(body);
}

async function collect(response: Response): Promise<SSEEvent[]> {
  const out: SSEEvent[] = [];
  for await (const e of readSSE(response)) out.push(e);
  return out;
}

test("parsea eventos con nombre y datos JSON", async () => {
  const events = await collect(responseFrom([
    'event: status\ndata: {"stage": "buscando"}\n\n',
    'event: final\ndata: {"status": "verified", "message": null, "problems": []}\n\n',
  ]));
  assert.deepEqual(events, [
    { event: "status", data: { stage: "buscando" } },
    { event: "final", data: { status: "verified", message: null, problems: [] } },
  ]);
});

test("un evento partido en varios trozos de red se arma completo", async () => {
  const events = await collect(responseFrom(['eve', 'nt: token\nda', 'ta: {"text": "50 m', 'g", "block": 0}\n', '\n']));
  assert.deepEqual(events, [{ event: "token", data: { text: "50 mg", block: 0 } }]);
});

test("una letra con tilde partida entre dos trozos no se corrompe", async () => {
  const bytes = new TextEncoder().encode('event: token\ndata: {"text": "hipertensión"}\n\n');
  const cut = bytes.indexOf(0xc3) + 1; // en medio de los dos bytes de la "ó"
  const events = await collect(responseFrom([bytes.slice(0, cut), bytes.slice(cut)]));
  assert.deepEqual(events, [{ event: "token", data: { text: "hipertensión" } }]);
});

test("acepta finales de línea \\r\\n, ignora comentarios y une varias líneas data", async () => {
  const events = await collect(responseFrom([
    ": keep-alive\r\n\r\n",
    'event: sources\r\ndata: [{"n": 1,\r\ndata:  "year": 2017}]\r\n\r\n',
  ]));
  assert.deepEqual(events, [{ event: "sources", data: [{ n: 1, year: 2017 }] }]);
});

test("sin línea event el nombre es message", async () => {
  assert.deepEqual(await collect(responseFrom(['data: "hola"\n\n'])), [{ event: "message", data: "hola" }]);
});
