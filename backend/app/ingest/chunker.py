"""Agrupa párrafos en fragmentos que respetan la estructura de una guía clínica."""
import re
from dataclasses import dataclass, field

from .pdf_parser import STRENGTH, Paragraph

__all__ = ["STRENGTH", "Chunk", "chunk_paragraphs"]

# "3.1 PRIMERA LÍNEA", "2. Métodos": un título numerado manda sobre uno sin número del mismo tamaño
NUMBERED = re.compile(r"^\d+(\.\d+)*\.?\s")


@dataclass
class Chunk:
    section: str
    paragraphs: list[Paragraph] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.paragraphs)

    @property
    def page_start(self) -> int:
        return self.paragraphs[0].page

    @property
    def page_end(self) -> int:
        return self.paragraphs[-1].page


def _heading_rank(p: Paragraph) -> float:
    # Mismo tamaño de letra: "Recomendación 1" queda dentro de "3.1 PRIMERA LÍNEA", no la reemplaza
    return p.level if NUMBERED.match(p.text) else p.level + 0.5


def chunk_paragraphs(paragraphs: list[Paragraph], max_chars: int = 1500) -> list[Chunk]:
    chunks: list[Chunk] = []
    path: list[tuple[float, str]] = []  # pila de títulos: [(rango, texto)]
    current: list[Paragraph] = []
    prev_heading = False

    def section() -> str:
        return " > ".join(title for _, title in path)

    def flush():
        if current:
            chunks.append(Chunk(section=section(), paragraphs=current.copy()))
            current.clear()

    for p in paragraphs:
        if p.kind == "heading":
            flush()
            rank = _heading_rank(p)
            if prev_heading and path and path[-1][0] == rank:
                # Títulos seguidos del mismo nivel son uno solo partido en líneas:
                # "Recomendación 1" + "En personas adultas mayores…?"
                path[-1] = (rank, f"{path[-1][1]} {p.text}")
            else:
                path[:] = [h for h in path if h[0] < rank] + [(rank, p.text)]
            prev_heading = True
            continue
        prev_heading = False
        if p.kind == "table":
            flush()  # una tabla siempre va en su propio fragmento, con su sección
            chunks.append(Chunk(section=section(), paragraphs=[p]))
            continue

        glued = bool(STRENGTH.match(p.text))
        size = sum(len(x.text) for x in current)
        if current and not glued and size + len(p.text) > max_chars:
            flush()
        current.append(p)

    flush()
    return chunks
