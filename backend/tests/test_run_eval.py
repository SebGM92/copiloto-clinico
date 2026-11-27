"""El evaluador sin red: un corte de conexión no tumba la evaluación y las métricas se calculan bien."""
import asyncio
from types import SimpleNamespace as NS

from eval.run_eval import evaluate_full, run_with_retry


def state(status, text="", citations=()):
    return {"status": status, "problems": [], "chunks": [NS(paragraphs=[{"page": 4}])],
            "blocks": [NS(text=text, citations=list(citations))]}


def test_network_error_is_retried_and_then_recorded_as_error():
    calls = []

    async def flaky(question):
        calls.append(question)
        if len(calls) < 3:
            raise ConnectionResetError("reset")
        return {"status": "verified"}

    assert asyncio.run(run_with_retry(flaky, "q")) == {"status": "verified"}

    async def broken(question):
        raise ConnectionResetError("reset")

    assert asyncio.run(run_with_retry(broken, "q", attempts=2))["status"] == "error"


def test_metrics_including_false_answers():
    cite = NS(search_result_index=0, start_block_index=0, end_block_index=1, cited_text="Losartán 50 mg.")
    answers = {
        "a1": state("verified", "Losartán 50 mg.", [cite]),
        "a2": state("retracted", "Losartán 100 mg.", [cite]),
        "u1": state("abstained", "Las guías cargadas no responden esta pregunta."),
        "u2": state("verified", "Algo inventado.", [cite]),  # respuesta falsa
    }
    cases = [{"id": "a1", "question": "a1", "answerable": True, "pages": [4], "must_contain": ["50 mg"]},
             {"id": "a2", "question": "a2", "answerable": True, "pages": [4], "must_contain": ["50 mg"]},
             {"id": "u1", "question": "u1", "answerable": False},
             {"id": "u2", "question": "u2", "answerable": False}]
    saved = []

    async def run(q):
        return answers[q]

    m = asyncio.run(evaluate_full(cases, run, on_row=lambda rows: saved.append(len(rows))))
    assert m["answered_verified"] == 0.5 and m["false_answer_rate"] == 0.5
    assert m["retracted"] == 0.25 and m["must_contain"] == 1.0 and m["citation_precision"] == 1.0
    assert saved == [1, 2, 3, 4]  # se guarda después de cada caso


def test_judge_agreement_export_hides_verdict_and_scores(tmp_path, monkeypatch):
    import json

    import eval.judge_agreement as ja

    results = tmp_path / "results"
    results.mkdir()
    judged = [{"claim": f"c{i}", "quote": f"q{i}", "context": "", "judge": i % 3 != 0} for i in range(9)]
    (results / "full-x.json").write_text(json.dumps({"metrics": {"rows": [{"id": "a", "judged": judged}]}}))
    monkeypatch.setattr(ja, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(ja, "LABELS", tmp_path / "judge_labels.jsonl")

    sample = ja.export(results / "full-x.json", n=6)
    assert len(sample) == 6 and sum(not p["judge"] for p in sample) == 3  # todos los rechazados, hasta la mitad
    lines = (tmp_path / "judge_labels.jsonl").read_text().splitlines()
    assert all("judge" not in json.loads(line) for line in lines[1:])  # quien etiqueta no ve al juez

    labeled = [json.loads(lines[0])] + [{**json.loads(line), "human": True} for line in lines[1:]]
    (tmp_path / "judge_labels.jsonl").write_text("\n".join(json.dumps(x) for x in labeled))
    r = ja.score()
    assert r["labeled"] == 6 and r["agreement"] == 0.5  # la persona aceptó todo; el juez rechazó 3
