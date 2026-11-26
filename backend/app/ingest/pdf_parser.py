"""Extracción de texto desde PDFs de guías clínicas."""
from pathlib import Path

from pypdf import PdfReader


def parse_pdf(path: Path) -> list[tuple[int, str]]:
    """Devuelve una lista de (número de página, texto)."""
    reader = PdfReader(path)
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
