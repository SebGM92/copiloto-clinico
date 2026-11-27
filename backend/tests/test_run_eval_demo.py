"""El evaluador de punta a punta con la guía ficticia, Claude simulado y juez simulado (sin costo).

Corre `python -m eval.run_eval` como lo haría CI. Necesita la base (docker compose up -d db).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from app import config

BACKEND = Path(__file__).resolve().parent.parent


def run_eval(tmp_path, *extra):
    try:
        psycopg.connect(config.DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    report = tmp_path / "report.json"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # demuestra que no gasta tokens
    proc = subprocess.run(
        [sys.executable, "-m", "eval.run_eval", "eval/golden_ficticia.jsonl", "--mode", "full", "--demo", "--judge",
         "--report", str(report), *extra],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300,
    )
    return proc, json.loads(report.read_text())["metrics"] if report.exists() else None


def test_demo_end_to_end_meets_the_targets(tmp_path):
    proc, m = run_eval(tmp_path, "--min-hit", "0.85", "--max-false-answer", "0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    statuses = {r["id"]: r["status"] for r in m["rows"]}
    assert statuses == {"fic-01": "verified", "fic-02": "verified", "fic-03": "verified",
                        "fic-04": "abstained", "fic-05": "no_evidence"}
    assert m["false_answer_rate"] == 0 and m["must_contain"] == 1 and m["citation_precision"] == 1
    assert m["faithfulness"] == 1 and m["hit_rate"] == 1


def test_ci_gate_fails_with_exit_code_1(tmp_path):
    proc, _ = run_eval(tmp_path, "--min-hit", "1.01")
    assert proc.returncode == 1 and "NO CUMPLE" in proc.stdout
