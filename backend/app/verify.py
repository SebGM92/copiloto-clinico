"""Verificación determinista de la respuesta: corre después de generar y antes de confiar."""
import re
from dataclasses import dataclass, field

from .llm import AnswerBlock
from .retrieval import RetrievedChunk

ABSTENTION = "Las guías cargadas no responden esta pregunta."
# Un número pegado a una letra o unido con guion es parte de un nombre, no un dato clínico:
# "iDPP4", "DM2", "HbA1c", "SGLT2", "GLP-1", "PHQ-9", "CIE-10". Las dosis y metas siguen contando.
NUMBER = re.compile(r"(?<![\d.,])(?<![^\W\d_])(?<![^\W\d_]-)\d+(?:[.,]\d+)?")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


# "Anexo 6", "Tabla Nº 1", "Recomendación 3": el número nombra una parte de la guía, no es un dato clínico
REFERENCE = re.compile(
    r"\b(anexo|tabla|figura|cuadro|gr[aá]fico|flujograma|recomendaci[oó]n|pregunta|secci[oó]n|cap[ií]tulo)"
    r"\s*(n[º°o]\.?\s*)?\d+(?:\.\d+)*",
    re.IGNORECASE,
)


# Grado de recomendación de la guía de Depresión: "1 A", "2 B", "4 C" (nivel de evidencia + grado)
GRADE = re.compile(r"(?<![\w.,])([1-4])\s?([A-D])\b")


def grades(text: str) -> set[str]:
    return {f"{level}{letter}" for level, letter in GRADE.findall(text)}


def strip_cited_grades(text: str, cited: set[str]) -> str:
    """Quita un grado escrito fuera de la cita ("El grado es 1 A") si ese mismo grado aparece citado.

    Un grado que no figura en ninguna cita de la respuesta se deja: sus números se siguen revisando.
    """
    return GRADE.sub(lambda m: " " if f"{m.group(1)}{m.group(2)}" in cited else m.group(0), text)


def known_metadata(chunks: list[RetrievedChunk]) -> list[re.Pattern]:
    """Números que vienen de los datos de la guía entregada, no de su contenido clínico.

    - El año de la guía, como número completo: "(2017)".
    - Las frases numéricas de su título, con su palabra vecina: "tipo 2", "15 años".
      Solo la frase: un "2 comprimidos" suelto sigue contando como dato.
    """
    patterns = set()
    for c in chunks:
        patterns.add(rf"\b{c.year}\b")
        for m in re.finditer(r"(\w+)\s+(\d+)|(\d+)\s+(\w+)", c.title):
            patterns.add(r"\b" + r"\s+".join(map(re.escape, filter(None, m.groups()))) + r"\b")
    return [re.compile(p, re.IGNORECASE) for p in sorted(patterns)]


def strip_non_clinical(text: str, metadata: list[re.Pattern]) -> str:
    text = REFERENCE.sub(" ", text)
    for pattern in metadata:
        text = pattern.sub(" ", text)
    return text


def numbers(text: str) -> set[str]:
    """Números normalizados: '7,5' y '7.5' cuentan como el mismo."""
    without_markers = LIST_MARKER.sub(" ", text)
    return {n.replace(",", ".") for n in NUMBER.findall(without_markers)}


@dataclass
class SourceRef:
    n: int                 # número de la fuente en la interfaz (1, 2, 3...)
    chunk_id: int
    title: str
    year: int
    section: str
    url: str
    paragraphs: list[dict]  # [{"page": 4, "para": 2, "kind": "text"}]
    quote: str


@dataclass
class Verification:
    status: str                        # verified | retracted | abstained
    problems: list[str] = field(default_factory=list)
    refs: list[SourceRef] = field(default_factory=list)


def resolve(citation, chunks: list[RetrievedChunk]) -> SourceRef | None:
    if not 0 <= citation.search_result_index < len(chunks):
        return None
    chunk = chunks[citation.search_result_index]
    cited = chunk.paragraphs[citation.start_block_index:citation.end_block_index]
    if not cited:
        return None
    return SourceRef(
        n=citation.search_result_index + 1,
        chunk_id=chunk.id,
        title=chunk.title,
        year=chunk.year,
        section=chunk.section,
        url=f"{chunk.source_url}#page={cited[0]['page']}",
        paragraphs=[{"page": p["page"], "para": p["para"], "kind": p["kind"]} for p in cited],
        quote=citation.cited_text,
    )


def verify(blocks: list[AnswerBlock], chunks: list[RetrievedChunk]) -> Verification:
    full_text = "".join(b.text for b in blocks)
    total_citations = sum(len(b.citations) for b in blocks)

    if ABSTENTION in full_text or total_citations == 0:
        return Verification(status="abstained")

    problems, refs = [], []
    metadata = known_metadata(chunks)
    cited_grades = grades(" ".join(c.cited_text for b in blocks for c in b.citations))
    for b in blocks:
        text = b.text.strip()
        # Sin año, título ni "Anexo N"; sin un grado de recomendación que la respuesta sí cita en otra parte
        clinical = strip_cited_grades(strip_non_clinical(text, metadata), cited_grades)
        if not b.citations:
            if numbers(clinical):
                problems.append(f"Dato numérico sin cita: «{text[:120]}»")
            continue
        cited_text = " ".join(c.cited_text for c in b.citations)
        missing = numbers(clinical) - numbers(cited_text)
        if missing:
            problems.append(f"{', '.join(sorted(missing))} no aparece en el texto citado: «{text[:120]}»")
        for c in b.citations:
            ref = resolve(c, chunks)
            if ref is None:
                problems.append("Cita a una fuente que no fue entregada al modelo")
                continue
            expected = "".join(p["text"] for p in chunks[c.search_result_index].paragraphs[c.start_block_index:c.end_block_index])
            if re.sub(r"\s+", "", c.cited_text) != re.sub(r"\s+", "", expected):
                problems.append("El texto citado no coincide con la fuente")
            refs.append(ref)

    return Verification(status="retracted" if problems else "verified", problems=problems, refs=refs)
