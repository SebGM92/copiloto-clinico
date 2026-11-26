"""Agrupa párrafos en fragmentos que respetan la estructura de una guía clínica."""
import re
from dataclasses import dataclass, field

from .pdf_parser import Paragraph

# Líneas que califican a la recomendación anterior: nunca se separan de ella
STRENGTH = re.compile(
    r"^(recomendaci[oó]n (fuerte|condicional|d[eé]bil)|grado de recomendaci[oó]n|"
    r"nivel de evidencia|certeza (de la|en la) evidencia|calidad de (la )?evidencia)",
    re.IGNORECASE,
)


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


def chunk_paragraphs(paragraphs: list[Paragraph], max_chars: int = 1500) -> list[Chunk]:
    chunks: list[Chunk] = []
    path: list[tuple[int, str]] = []  # pila de títulos: [(nivel, texto)]
    current: list[Paragraph] = []

    def section() -> str:
        return " > ".join(title for _, title in path)

    def flush():
        if current:
            chunks.append(Chunk(section=section(), paragraphs=current.copy()))
            current.clear()

    for p in paragraphs:
        if p.kind == "heading":
            flush()
            path[:] = [h for h in path if h[0] < p.level] + [(p.level, p.text)]
            continue
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
