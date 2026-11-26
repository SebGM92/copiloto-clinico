"""CLI de ingesta: python -m app.ingest.cli <carpeta_pdfs>"""
import argparse
from collections import Counter
from pathlib import Path

from app.ingest.pdf_parser import parse_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de guías clínicas")
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()

    for pdf in sorted(args.folder.glob("*.pdf")):
        paragraphs = parse_pdf(str(pdf))
        kinds = Counter(p.kind for p in paragraphs)
        pages = len({p.page for p in paragraphs})
        print(f"{pdf.name}: {pages} páginas, {dict(kinds)}")
        # TODO: agrupar en fragmentos por sección, generar embeddings y guardar en la base


if __name__ == "__main__":
    main()
