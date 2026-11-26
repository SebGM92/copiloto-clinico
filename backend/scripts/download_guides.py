"""Descarga las guías de corpus.json a backend/guias/ y las ingesta en PostgreSQL.

Uso (desde backend/, con el .env cargado):
    python -m scripts.download_guides
"""
import json
from pathlib import Path

import httpx
import psycopg

from app import config
from app.embeddings import BgeM3Embedder
from app.ingest.cli import ingest

BACKEND = Path(__file__).resolve().parent.parent
CORPUS = BACKEND / "corpus.json"
OUT = BACKEND / "guias"


class LazyBgeM3:
    """Carga bge-m3 (~10 s) solo si alguna guía cambió y hay que generar embeddings."""

    dim = 1024

    def __init__(self):
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            self._model = BgeM3Embedder(config.EMBEDDING_MODEL)
        return self._model.embed(texts)


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"ya descargada: {dest.name}")
        return
    r = httpx.get(url, follow_redirects=True, timeout=120)
    r.raise_for_status()
    # Algunas filas de la tabla de DIPRECE enlazan a una página HTML, no al PDF
    if not r.content.startswith(b"%PDF"):
        raise ValueError(f"{url} no devolvió un PDF ({r.headers.get('content-type')}): "
                         "busca el enlace directo al PDF en esa página")
    dest.write_bytes(r.content)
    print(f"descargada: {dest.name} ({len(r.content) // 1024} KB)")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    guides = json.loads(CORPUS.read_text(encoding="utf-8"))
    embedder = LazyBgeM3()
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        for g in guides:
            pdf = OUT / f"{g['slug']}.pdf"
            download(g["url"], pdf)
            ingest(conn, embedder, str(pdf), slug=g["slug"], title=g["title"], year=g["year"],
                   url=g["url"], publisher=g.get("publisher", "MINSAL"))


if __name__ == "__main__":
    main()
