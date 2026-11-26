"""Agrupa párrafos en fragmentos que respetan la estructura de una guía clínica."""
from dataclasses import dataclass, field

from .pdf_parser import STRENGTH, Paragraph, section_key

__all__ = ["STRENGTH", "Chunk", "chunk_paragraphs"]


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


@dataclass
class _Title:
    key: tuple[int, ...] | None  # (5, 1, 2) si el título está numerado
    level: int                   # nivel por tamaño de letra (1 = más grande)
    text: str


def chunk_paragraphs(paragraphs: list[Paragraph], max_chars: int = 1500) -> list[Chunk]:
    chunks: list[Chunk] = []
    path: list[_Title] = []           # títulos numerados primero, luego los sin número que cuelgan del último
    last_key: tuple[int, ...] = ()    # última numeración de sección vista
    current: list[Paragraph] = []
    caption: Paragraph | None = None  # "Tabla 2: …" esperando su tabla
    prev_heading = False
    # Nivel de los capítulos numerados ("1. INTRODUCCIÓN"). Un título sin número con letra más grande
    # es de portada ("Depresión", "en personas de 15 años y más") y no entra en la ruta de sección.
    chapter_levels = [p.level for p in paragraphs if p.kind == "heading" and len(section_key(p.text) or ()) == 1]
    chapter_level = min(chapter_levels, default=0)

    def section() -> str:
        return " > ".join(t.text for t in path)

    def flush():
        if current:
            chunks.append(Chunk(section=section(), paragraphs=current.copy()))
            current.clear()

    def release_caption():
        nonlocal caption
        if caption:  # el rótulo no tenía tabla detrás (tabla como imagen): queda como texto
            current.append(caption)
            caption = None

    for p in paragraphs:
        if p.kind == "heading":
            release_caption()
            flush()
            key = section_key(p.text)
            if key is None and p.level < chapter_level:
                prev_heading = False
                continue  # título de portada: ya está en documents.title
            if key is not None and key <= last_key:
                key = None  # "1. Fármaco versus placebo" dentro de 5.3.2 es una lista, no una sección nueva
            if key is not None:
                # La numeración manda: 5.1.2 cuelga de 5.1 y de 5, y nunca de un título sin número
                last_key = key
                path[:] = [t for t in path if t.key and key[:len(t.key)] == t.key] + [_Title(key, p.level, p.text)]
            elif prev_heading and path and path[-1].key is None and path[-1].level == p.level:
                # Títulos sin número seguidos y del mismo nivel son uno solo: "Recomendación 1" + su pregunta
                path[-1].text = f"{path[-1].text} {p.text}"
            else:
                top = next((t for t in path if t.key), None)
                if top and p.level <= top.level:
                    path[:] = [_Title(None, p.level, p.text)]  # "REFERENCIAS": tan grande como un capítulo
                else:
                    path[:] = [t for t in path if t.key or t.level < p.level] + [_Title(None, p.level, p.text)]
            prev_heading = True
            continue
        prev_heading = False

        if p.kind == "caption":
            release_caption()
            caption = p
            continue
        if p.kind == "table":
            flush()  # una tabla siempre va en su propio fragmento, con su sección y su rótulo
            chunks.append(Chunk(section=section(), paragraphs=[caption, p] if caption else [p]))
            caption = None
            continue

        release_caption()
        glued = bool(STRENGTH.match(p.text))
        size = sum(len(x.text) for x in current)
        if current and not glued and size + len(p.text) > max_chars:
            flush()
        current.append(p)

    release_caption()
    flush()
    return chunks
