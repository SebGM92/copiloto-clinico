"""Servidor de desarrollo sin costo para trabajar el frontend: sin API key y sin bge-m3.

Levanta la API real en http://localhost:8000 con:
- una base aparte (rag_demo) con solo la guía FICTICIA, para no mezclarla con las guías reales;
- el embedder de hashing (no descarga modelos);
- un Claude simulado que responde con citas armadas como las de la API real.

Uso (desde backend/, con `docker compose up -d db`):
    python -m tests.demo_server

Preguntas de ejemplo:
- "¿Cuál es la dosis máxima de amlodipino?"   -> verified, cita a una tabla
- "¿Con qué fármaco se inicia la HTA?"         -> verified, losartán con su fuerza de recomendación
- "¿Qué tratamiento de la HTA se usa en el embarazo?" -> abstained
- "¿Qué vacuna contra el sarampión se usa?"    -> no_evidence (no llega al modelo)
- "Paciente 12.345.678-5 con HTA"              -> blocked
La guía ficticia dice ser de 2017, para ver la advertencia de guía antigua.
"""
import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

DEMO_DB = "rag_demo"
BASE_URL = os.environ.get("DATABASE_URL", "postgresql://rag:rag@localhost:5433/rag")
DEMO_URL = BASE_URL.rsplit("/", 1)[0] + f"/{DEMO_DB}"
os.environ["DATABASE_URL"] = DEMO_URL  # antes de importar app.config

import httpx2  # noqa: E402
import psycopg  # noqa: E402
import uvicorn  # noqa: E402
from anthropic import AsyncAnthropic  # noqa: E402

from app.embeddings import HashingEmbedder  # noqa: E402
from app.ingest.cli import ingest  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fake_anthropic import FakeAnthropic  # noqa: E402
from tests.make_fake_guide import LOSARTAN, make_fake_guide  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
DEMO_MIN_SIMILARITY = 0.3  # hashing: con respuesta 0.37-0.46, sarampión 0.12
STRENGTH = "Recomendación fuerte, certeza de la evidencia moderada."
ABSTENTION = ("Las guías cargadas no responden esta pregunta. "
              "La guía cargada cubre el tratamiento farmacológico de la hipertensión en adultos y su seguimiento.")


def prepare_database() -> None:
    with psycopg.connect(BASE_URL, autocommit=True) as admin:
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DEMO_DB,)).fetchone():
            admin.execute(f"CREATE DATABASE {DEMO_DB}")
    with psycopg.connect(DEMO_URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
        pdf = make_fake_guide(Path(tempfile.mkdtemp()) / "guia_ficticia.pdf")
        ingest(conn, HashingEmbedder(), str(pdf), slug="demo-hta-ficticia", title="Guía FICTICIA de hipertensión",
               year=2017, url="https://example.org/guia-ficticia-hta.pdf", publisher="Ministerio Ficticio")


class DemoAnthropic(FakeAnthropic):
    """Elige el guion según la pregunta y entrega los eventos de a poco, como la API real."""

    def script_for(self, question: str) -> list[tuple[str, str | None]]:
        q = question.lower()
        if "embarazo" in q:
            return [(ABSTENTION, None)]
        if "amlodipino" in q:
            return [("Según la tabla de dosis de la guía, ", None),
                    ("la dosis máxima de amlodipino es 10 mg.", "| Amlodipino |")]
        return [("Se recomienda iniciar losartán 50 mg al día en adultos con hipertensión arterial y diabetes",
                 LOSARTAN[:40]),
                (", con recomendación fuerte y certeza de la evidencia moderada.", STRENGTH)]

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        question = body["messages"][0]["content"][-1]["text"]
        self.script = self.script_for(question)
        whole = super().handle(request).content.decode()

        async def drip():
            for event in whole.split("\n\n"):
                if event:
                    await asyncio.sleep(0.15)
                    yield (event + "\n\n").encode()

        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=drip())


def main() -> None:
    prepare_database()
    fake = DemoAnthropic()
    client = AsyncAnthropic(api_key="sk-demo", http_client=httpx2.AsyncClient(transport=fake.transport()))
    print(f"Demo con la guía ficticia en {DEMO_URL}. API en http://localhost:8000")
    # Umbral para el embedder de hashing (sus similitudes son mucho más bajas que las de bge-m3)
    uvicorn.run(create_app(embedder=HashingEmbedder(), client=client, min_similarity=DEMO_MIN_SIMILARITY),
                host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
