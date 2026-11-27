"""¿Cuánto coincide el juez (Claude Haiku 5.5) con una persona?

1) Exportar pares afirmación-cita de una evaluación full --judge:
       python -m eval.judge_agreement export eval/results/full-XXXX.json --n 20
   Escribe eval/judge_labels.jsonl SIN el veredicto del juez, para no sesgar a quien etiqueta.
2) Etiquetar a mano: en cada línea, cambiar "human": null por true (la cita respalda TODA la
   afirmación, incluidos números y unidades) o false.
3) Medir el acuerdo:
       python -m eval.judge_agreement score
"""
import argparse
import json
import random
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
LABELS = EVAL_DIR / "judge_labels.jsonl"


def collect_pairs(results_path: Path) -> list[dict]:
    rows = json.loads(results_path.read_text())["metrics"]["rows"]
    return [{"case": r["id"], "i": i, **j} for r in rows for i, j in enumerate(r.get("judged", []))]


def export(results_path: Path, n: int, seed: int = 7) -> list[dict]:
    """Muestra n pares: todos los que el juez rechazó (hasta la mitad) y el resto al azar entre los aceptados."""
    pairs = collect_pairs(results_path)
    if not pairs:
        raise SystemExit(f"{results_path} no tiene pares juzgados: corre `--mode full --judge` primero")
    rng = random.Random(seed)
    rejected = [p for p in pairs if not p["judge"]]
    accepted = [p for p in pairs if p["judge"]]
    sample = rng.sample(rejected, min(len(rejected), n // 2))
    sample += rng.sample(accepted, min(len(accepted), n - len(sample)))
    rng.shuffle(sample)
    with LABELS.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"source": str(results_path.name)}, ensure_ascii=False) + "\n")
        for p in sample:
            f.write(json.dumps({"case": p["case"], "i": p["i"], "claim": p["claim"].strip(),
                                "quote": p["quote"].strip(), "human": None}, ensure_ascii=False) + "\n")
    return sample


def score() -> dict:
    lines = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines() if line.strip()]
    source, labels = lines[0]["source"], lines[1:]
    judged = {(p["case"], p["i"]): p["judge"] for p in collect_pairs(EVAL_DIR / "results" / source)}
    done = [lab for lab in labels if lab["human"] is not None]
    if not done:
        raise SystemExit(f"Ningún par etiquetado todavía en {LABELS.name}")
    agree = [judged[(lab["case"], lab["i"])] == lab["human"] for lab in done]
    disagreements = [lab for lab, ok in zip(done, agree) if not ok]
    return {"labeled": len(done), "pending": len(labels) - len(done),
            "agreement": sum(agree) / len(agree), "disagreements": disagreements}


def main() -> None:
    parser = argparse.ArgumentParser(description="Acuerdo entre el juez y una persona")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("results", type=Path)
    e.add_argument("--n", type=int, default=20)
    sub.add_parser("score")
    args = parser.parse_args()
    if args.cmd == "export":
        sample = export(args.results, args.n)
        print(f"{len(sample)} pares en {LABELS.relative_to(EVAL_DIR.parent)}: etiqueta cada uno con true o false")
    else:
        r = score()
        print(f"Acuerdo juez-persona: {r['agreement']:.0%} en {r['labeled']} pares ({r['pending']} pendientes)")
        for d in r["disagreements"]:
            print(f"  [{d['case']}] persona={d['human']} · «{d['claim'][:90]}»")


if __name__ == "__main__":
    main()
