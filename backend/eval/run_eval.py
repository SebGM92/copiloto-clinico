"""Evaluación del copiloto con el set dorado.

Modos:
    python -m eval.run_eval retrieval            # gratis: ¿llega la página correcta al modelo?
    python -m eval.run_eval full                 # grafo completo con Claude (gasta tokens)
    python -m eval.run_eval full --judge         # + juez Claude Haiku 5.5 para faithfulness
Opciones:
    --golden RUTA   set dorado (por defecto eval/golden.jsonl)
    --limit N       solo los primeros N casos
    --demo          base rag_demo, embedder de hashing y Claude simulado: prueba el evaluador sin costo
                    (usar con --golden eval/golden_ficticia.jsonl)
Los resultados quedan en eval/results/<modo>-<fecha>.json.
"""
import sys

DEMO = "--demo" in sys.argv
if DEMO:
    import tests.demo_server  # noqa: F401  (apunta DATABASE_URL a rag_demo antes de importar app.config)

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from anthropic import AsyncAnthropic  # noqa: E402
from psycopg_pool import AsyncConnectionPool  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import config  # noqa: E402
from app.embeddings import BgeM3Embedder, HashingEmbedder  # noqa: E402
from app.graph import build_graph  # noqa: E402
from app.retrieval import hybrid_search  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-haiku-5-5")

TARGETS = {  # metas iniciales de la guía: un punto de partida, no un estándar
    "hit_rate": (">=", 0.85), "mrr": (">=", 0.6), "false_answer_rate": ("<=", 0.0),
    "answered_verified": (">=", 0.8), "must_contain": (">=", 0.9), "citation_precision": (">=", 0.8),
    "faithfulness": (">=", 0.95),
}


def load_cases(path: Path, limit: int | None) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return cases[:limit] if limit else cases


def is_hit(chunk, case: dict) -> bool:
    """El fragmento es de la guía correcta y cubre alguna de las páginas esperadas."""
    return chunk.slug == case["doc"] and any(chunk.page_start <= p <= chunk.page_end for p in case["pages"])


def mean_of_bool(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


async def evaluate_retrieval(cases: list[dict], search) -> dict:
    """search(question) -> list[RetrievedChunk]. Mide si la página correcta llega al modelo."""
    hits, reciprocal, similarity = [], [], {True: [], False: []}
    for case in cases:
        chunks = await search(case["question"])
        best = max((c.similarity or 0 for c in chunks), default=0)
        similarity[case["answerable"]].append(round(best, 3))
        if not case["answerable"]:
            continue
        rank = next((i + 1 for i, ch in enumerate(chunks) if is_hit(ch, case)), None)
        hits.append(rank is not None)
        reciprocal.append(1 / rank if rank else 0.0)
        if rank is None:
            print(f"  [falla] {case['id']}: la página esperada no está en el top {len(chunks)}")
    return {
        "hit_rate": statistics.mean(hits), "mrr": statistics.mean(reciprocal), "n": len(hits),
        # Para calibrar MIN_SIMILARITY: el umbral debe quedar entre estas dos listas
        "best_similarity_answerable": sorted(similarity[True]),
        "best_similarity_unanswerable": sorted(similarity[False]),
    }


async def run_with_retry(run, question: str, attempts: int = 3) -> dict:
    """El SDK reintenta al iniciar la petición, no si la conexión se corta a mitad del streaming."""
    for attempt in range(1, attempts + 1):
        try:
            return await run(question)
        except Exception as e:  # noqa: BLE001  (error de red, 5xx, etc.)
            print(f"    [intento {attempt}/{attempts}] {type(e).__name__}: {str(e)[:100]}")
            if attempt == attempts:
                return {"status": "error", "problems": [f"{type(e).__name__}: {e}"]}
            await asyncio.sleep(2 * attempt)


async def evaluate_full(cases: list[dict], run, judge=None, on_row=None) -> dict:
    """run(question) -> estado final del grafo. judge(claim, quote, context) -> bool."""
    rows = []
    for case in cases:
        started = time.monotonic()
        state = await run_with_retry(run, case["question"])
        latency = time.monotonic() - started
        answer = "".join(b.text for b in state.get("blocks", []))
        row = {"id": case["id"], "answerable": case["answerable"], "status": state.get("status"), "latency": latency}

        if case["answerable"]:
            row["contains"] = all(s.lower() in answer.lower() for s in case.get("must_contain", []))
            cited_pages = [
                p["page"]
                for b in state.get("blocks", []) for c in b.citations
                for p in state["chunks"][c.search_result_index].paragraphs[c.start_block_index:c.end_block_index]
            ]
            if cited_pages and case.get("pages"):
                row["citation_precision"] = sum(p in case["pages"] for p in cited_pages) / len(cited_pages)

        if judge and row["status"] == "verified":
            # Cada bloque es a veces un fragmento ("<8 %"): el juez recibe la respuesta completa como contexto
            verdicts = [await judge(b.text, " ".join(c.cited_text for c in b.citations), answer)
                        for b in state["blocks"] if b.citations]
            row["faithfulness"] = sum(verdicts) / len(verdicts) if verdicts else None
        row["problems"] = state.get("problems", [])
        row["answer"] = answer
        rows.append(row)
        print(f"  {case['id']}: {row['status']}" + (f" — {row['problems'][0][:110]}" if row["problems"] else ""))
        if on_row:
            on_row(rows)  # guardado parcial: un corte no borra lo ya evaluado

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    latencies = sorted(r["latency"] for r in rows)

    def mean_of(key, subset):
        values = [r[key] for r in subset if r.get(key) is not None]
        return statistics.mean(values) if values else None

    return {
        "answered_verified": mean_of_bool([r["status"] == "verified" for r in answerable]),
        "retracted": mean_of_bool([r["status"] == "retracted" for r in rows]),
        "errors": sum(r["status"] == "error" for r in rows),
        # La métrica más importante: responder algo que las guías no dicen
        "false_answer_rate": mean_of_bool([r["status"] == "verified" for r in unanswerable]),
        "must_contain": mean_of_bool([r.get("contains", False) for r in answerable if r["status"] == "verified"]),
        "citation_precision": mean_of("citation_precision", answerable),
        "faithfulness": mean_of("faithfulness", rows),
        "latency_p50_s": latencies[len(latencies) // 2] if latencies else None,
        "latency_p95_s": latencies[int(len(latencies) * 0.95) - 1] if latencies else None,
        "rows": rows,
    }


class Verdict(BaseModel):
    supported: bool
    reason: str


JUDGE_PROMPT = """Eres un revisor clínico estricto. Decide si la CITA respalda por completo la AFIRMACIÓN.
- Números, dosis, unidades, umbrales y grados de recomendación deben coincidir con la cita.
- Si la afirmación agrega algo que la cita no dice, o cambia su sentido, NO está respaldada.
- Parafrasear está bien si el significado clínico es el mismo.
- La AFIRMACIÓN puede ser un fragmento de una frase (por ejemplo "<8 %" o "grado 1 A"). Usa la RESPUESTA
  COMPLETA solo para entender a qué se refiere el fragmento; juzga únicamente lo que afirma ese fragmento."""


def make_judge(client: AsyncAnthropic):
    async def judge(claim: str, quote: str, context: str = "") -> bool:
        response = await client.messages.parse(
            model=JUDGE_MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            system=JUDGE_PROMPT,
            messages=[{"role": "user", "content": f"RESPUESTA COMPLETA (contexto):\n{context.strip()}\n\n"
                                                  f"AFIRMACIÓN:\n{claim.strip()}\n\nCITA:\n{quote.strip()}"}],
            output_format=Verdict,
        )
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            print(f"    [juez] sin veredicto ({response.stop_reason}): se cuenta como no respaldada")
            return False
        if not response.parsed_output.supported:
            print(f"    [juez] no respaldada: «{claim.strip()[:80]}» — {response.parsed_output.reason[:120]}")
        return response.parsed_output.supported
    return judge


def print_summary(metrics: dict) -> None:
    print("\n| Métrica | Valor | Meta |\n|---|---|---|")
    for key, value in metrics.items():
        if key in ("rows",) or isinstance(value, list):
            continue
        goal = TARGETS.get(key)
        shown = "—" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))
        mark = ""
        if goal and value is not None:
            ok = value >= goal[1] if goal[0] == ">=" else value <= goal[1]
            mark = " ✓" if ok else " ✗"
        print(f"| {key} | {shown}{mark} | {f'{goal[0]} {goal[1]}' if goal else ''} |")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación con el set dorado")
    parser.add_argument("mode", choices=["retrieval", "full"])
    parser.add_argument("--golden", type=Path, default=EVAL_DIR / "golden.jsonl")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        from tests.demo_server import DemoAnthropic, prepare_database
        import httpx2
        prepare_database()
        embedder = HashingEmbedder()
        client = AsyncAnthropic(api_key="sk-demo", http_client=httpx2.AsyncClient(transport=DemoAnthropic().transport()))
    else:
        embedder = BgeM3Embedder(config.EMBEDDING_MODEL)
        client = AsyncAnthropic()

    cases = load_cases(args.golden, args.limit)
    out = EVAL_DIR / "results" / f"{args.mode}{'-demo' if args.demo else ''}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)

    def save(metrics_or_rows):
        payload = metrics_or_rows if isinstance(metrics_or_rows, dict) else {"partial_rows": metrics_or_rows}
        out.write_text(json.dumps({"golden": args.golden.name, "model": config.ANTHROPIC_MODEL, "metrics": payload},
                                  ensure_ascii=False, indent=2, default=str))
    print(f"{len(cases)} casos de {args.golden.name} · modo {args.mode}{' · demo' if args.demo else ''}")
    async with AsyncConnectionPool(config.DATABASE_URL, open=False) as pool:
        if args.mode == "retrieval":
            async def search(question):
                vector = (await asyncio.to_thread(embedder.embed, [question]))[0]
                async with pool.connection() as conn:
                    return await hybrid_search(conn, question, vector, k=config.TOP_K)
            metrics = await evaluate_retrieval(cases, search)
        else:
            min_similarity = 0.3 if args.demo else config.MIN_SIMILARITY  # hashing da similitudes más bajas
            graph = build_graph(pool, embedder, client, min_similarity=min_similarity)
            judge = make_judge(AsyncAnthropic()) if args.judge else None
            metrics = await evaluate_full(cases, lambda q: graph.ainvoke({"question": q}), judge, on_row=save)

    print_summary(metrics)
    if args.mode == "retrieval":
        print("\nMejor similitud con respuesta:", metrics["best_similarity_answerable"])
        print("Mejor similitud sin respuesta:", metrics["best_similarity_unanswerable"])
    save(metrics)
    print(f"\nResultados en {out.relative_to(EVAL_DIR.parent)}")


if __name__ == "__main__":
    asyncio.run(main())
