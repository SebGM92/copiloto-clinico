"""CLI de ingesta: python -m app.ingest.cli <carpeta_pdfs>"""
import argparse
from pathlib import Path

from app.ingest.chunker import chunk_text
from app.ingest.pdf_parser import parse_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de guías clínicas")
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()

    for pdf in sorted(args.folder.glob("*.pdf")):
        pages = parse_pdf(pdf)
        n = sum(len(chunk_text(text)) for _, text in pages)
        print(f"{pdf.name}: {len(pages)} páginas, {n} chunks")
        # TODO: generar embeddings y guardar en la base de datos


if __name__ == "__main__":
    main()
