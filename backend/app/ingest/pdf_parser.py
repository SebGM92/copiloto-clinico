"""Extrae párrafos de un PDF conservando página y número de párrafo."""
import re
import statistics
from collections import Counter
from dataclasses import dataclass

import pymupdf


@dataclass
class Paragraph:
    page: int        # página física del PDF, desde 1 (la que abre /guia.pdf#page=N)
    para: int        # número de párrafo de contenido en esa página, desde 1 (0 en títulos)
    text: str
    kind: str        # "heading" | "text" | "table" | "caption" (título de tabla o figura)
    level: int = 0   # nivel del título (1 = más grande); 0 si no es título


MARGIN = 0.08  # 8 % de cada borde de la página: zona de encabezados y pies (también laterales)

# Líneas que califican a la recomendación anterior. Nunca son título aunque vayan en negrita.
STRENGTH = re.compile(
    r"^(recomendaci[oó]n (fuerte|condicional|d[eé]bil)|grado de recomendaci[oó]n|"
    r"nivel de evidencia|certeza (de la|en la) evidencia|calidad de (la )?evidencia)",
    re.IGNORECASE,
)

# Página de flujograma dibujado con texto vectorial: muchas etiquetas cortas sobre muchos trazos
FIGURE_MIN_RUNS = 20
FIGURE_SHORT_RATIO = 0.6
FIGURE_SHORT_CHARS = 40
FIGURE_MIN_DRAWINGS = 20

TERMINAL = re.compile(r"[.:;!?]$")
BULLET = re.compile(r"^[•·◦▪\-−–—]")  # un ítem de lista nunca es título, aunque vaya en negrita

# "Tabla Nº 1: …", "Figura 2 …": rótulo de una tabla o figura, no un título de sección
CAPTION = re.compile(r"^(tabla|cuadro|figura|gr[aá]fico)\s*(n[º°o]\.?\s*)?\d+", re.IGNORECASE)
# Línea de índice: "1.2. Criterios diagnósticos..............16"
TOC_LEADER = re.compile(r"\.{8,}")
TOC_TITLE = re.compile(r"^(í|i)ndice( general)?$|^(tabla de )?contenidos?$", re.IGNORECASE)
# Numeración de sección: "1.", "3.1", "5.1.2." (hasta 2 dígitos: "2016 - 2017" no es una sección) y anexos
SECTION_NUMBER = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s")
ANNEX = re.compile(r"^anexo\s+(\d{1,2})\b", re.IGNORECASE)


def section_key(text: str) -> tuple[int, ...] | None:
    """(5, 1, 2) para "5.1.2. Síntesis"; los anexos van después de todas las secciones."""
    if m := ANNEX.match(text):
        return (1000 + int(m.group(1)),)
    if m := SECTION_NUMBER.match(text):
        return tuple(int(x) for x in m.group(1).split("."))
    return None


def _join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # "hiperten-" + "sión" -> "hipertensión"; en tablas también "ESTU-" + "DIOS"
        hyphenated = (text.endswith("-") and len(text) > 1 and text[-2].isalpha() and line[:1].isalpha()
                      and (line[:1].islower() or text[-2].isupper()))
        if hyphenated:
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return re.sub(r"\s+", " ", text).strip()


def _signature(text: str) -> str:
    """Firma para detectar encabezados repetidos: sin números ni mayúsculas."""
    return re.sub(r"\d+", "#", text.lower()).strip()


def _table_markdown(rows: list[list[str | None]]) -> str:
    clean = [[_join_lines((cell or "").splitlines()) for cell in row] for row in rows]
    header, body = clean[0], clean[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def _is_toc_table(rows: list[list[str]]) -> bool:
    """Índice armado como tabla: la última columna son números de página que solo crecen."""
    if len(rows) < 4:
        return False
    last = [row[-1].strip() for row in rows]
    if not all(re.fullmatch(r"\d{1,3}", x) for x in last):
        return False
    pages = [int(x) for x in last]
    return pages == sorted(pages) and not any(re.fullmatch(r"[\d.,\s]*", row[0]) for row in rows)


def _line_style(line: dict) -> tuple[float, bool]:
    spans = [s for s in line["spans"] if s["text"].strip()]
    size = round(max(s["size"] for s in spans), 1)
    bold = all(s["flags"] & 16 for s in spans)  # flag 16 = negrita
    return size, bold


def _in_margin(b: dict) -> bool:
    w, h = b["width"], b["height"]
    return (b["y1"] < h * MARGIN or b["y0"] > h * (1 - MARGIN)
            or b["x1"] < w * MARGIN or b["x0"] > w * (1 - MARGIN))


def _is_figure_page(page: pymupdf.Page, blocks: list[dict]) -> bool:
    """Flujograma con texto vectorial: etiquetas cortas y sueltas ("Sí", "No", "¿Cumple meta?")."""
    runs = [b for b in blocks if b["kind"] == "text" and not _in_margin(b)]
    if len(runs) < FIGURE_MIN_RUNS:
        return False
    short = sum(len(b["text"]) < FIGURE_SHORT_CHARS for b in runs) / len(runs)
    return short >= FIGURE_SHORT_RATIO and len(page.get_drawings()) >= FIGURE_MIN_DRAWINGS


def _raw_blocks(doc: pymupdf.Document) -> list[list[dict]]:
    pages = []
    for page in doc:
        width, height = page.rect.width, page.rect.height
        tables = page.find_tables().tables
        table_rects = [pymupdf.Rect(t.bbox) for t in tables]
        blocks = []
        for b in page.get_text("dict", sort=True)["blocks"]:
            if b["type"] != 0:  # 0 = texto; 1 = imagen
                continue
            if any(pymupdf.Rect(b["bbox"]).intersects(tr) for tr in table_rects):
                continue  # el texto de la tabla sale aparte, como markdown
            # PyMuPDF a veces junta un título y el texto siguiente en un mismo bloque:
            # partimos el bloque cada vez que cambia el estilo de la línea.
            runs: list[dict] = []
            for line in b["lines"]:
                if not any(s["text"].strip() for s in line["spans"]):
                    continue
                style = _line_style(line)
                text = "".join(s["text"] for s in line["spans"])
                # Sin superíndices: "Presentación clínica¹" -> "Presentación clínica" (solo para títulos)
                plain = "".join(s["text"] for s in line["spans"] if not s["flags"] & 1)
                x0, y0, x1, y1 = line["bbox"]
                if runs and runs[-1]["style"] == style:
                    r = runs[-1]
                    r["lines"].append(text)
                    r["plain"].append(plain)
                    r["y1"], r["x0"], r["x1"] = y1, min(r["x0"], x0), max(r["x1"], x1)
                else:
                    runs.append({"style": style, "lines": [text], "plain": [plain],
                                 "x0": x0, "y0": y0, "x1": x1, "y1": y1})
            for run in runs:
                blocks.append({
                    "x0": run["x0"], "y0": run["y0"], "x1": run["x1"], "y1": run["y1"],
                    "width": width, "height": height,
                    "text": _join_lines(run["lines"]), "plain": _join_lines(run["plain"]),
                    "size": run["style"][0], "bold": run["style"][1], "kind": "text",
                })
        for t in tables:
            # get_textbox por celda conserva los espacios mejor que t.extract()
            rows = [[page.get_textbox(cell) if cell else "" for cell in row.cells] for row in t.rows]
            clean = [[_join_lines((c or "").splitlines()) for c in row] for row in rows]
            text = _table_markdown(rows)
            blocks.append({
                "x0": t.bbox[0], "y0": t.bbox[1], "x1": t.bbox[2], "y1": t.bbox[3],
                "width": width, "height": height, "text": text, "plain": text, "size": 0, "bold": False,
                "kind": "toc" if _is_toc_table(clean) else "table",
            })
        if _is_figure_page(page, blocks):
            for b in blocks:
                if b["kind"] == "text" and not _in_margin(b):
                    b["kind"] = "figure"  # se descarta: ver README, limitaciones
        pages.append(sorted(blocks, key=lambda b: b["y0"]))
    return pages


def _repeated_margin_text(pages: list[list[dict]]) -> set[str]:
    """Textos en los márgenes que se repiten en al menos la mitad de las páginas."""
    if len(pages) < 3:
        return set()
    counts = Counter()
    for blocks in pages:
        counts.update({_signature(b["text"]) for b in blocks if _in_margin(b)})
    return {sig for sig, n in counts.items() if n >= len(pages) / 2}


def parse_pdf(path: str) -> list[Paragraph]:
    doc = pymupdf.open(path)
    pages = _raw_blocks(doc)
    repeated = _repeated_margin_text(pages)

    text_sizes = [b["size"] for blocks in pages for b in blocks if b["kind"] == "text" for _ in range(len(b["text"]))]
    body_size = statistics.median(text_sizes) if text_sizes else 10
    heading_sizes = sorted({b["size"] for blocks in pages for b in blocks
                            if b["kind"] == "text" and b["size"] >= body_size + 1.5}, reverse=True)

    paragraphs: list[Paragraph] = []
    bullet = ""  # viñeta que quedó sola en su línea ("−−"): se pega al ítem que sigue
    for page_no, blocks in enumerate(pages, start=1):
        para = 0
        for b in blocks:
            text = b["text"]
            if b["kind"] in ("figure", "toc") or (b["kind"] == "text" and TOC_LEADER.search(text)):
                continue  # flujograma vectorial o índice de la guía: no es contenido
            if _in_margin(b) and (_signature(text) in repeated or text.strip().isdigit()):
                continue  # encabezado, pie o número de página
            if b["kind"] == "text" and not re.search(r"\w", text):
                bullet = "– "
                continue
            if bullet and b["kind"] == "text":
                text, bullet = bullet + text, ""

            kind, level = b["kind"], 0
            if kind == "text" and (STRENGTH.match(text) or BULLET.match(text)):
                pass  # la fuerza de la recomendación y los ítems de lista son contenido, aunque vayan en negrita
            elif kind == "text" and b["size"] in heading_sizes:
                kind, level = "heading", heading_sizes.index(b["size"]) + 1
            elif kind == "text" and b["bold"] and len(text) < 120 and not text.endswith("."):
                kind, level = "heading", len(heading_sizes) + 1

            prev = paragraphs[-1] if paragraphs else None
            if kind == "heading":
                text = b["plain"] or text  # sin llamadas a nota al pie
                if TOC_TITLE.match(text.strip()):
                    continue  # el título "ÍNDICE": su contenido ya se descartó
                if CAPTION.match(text):
                    paragraphs.append(Paragraph(page=page_no, para=0, text=text, kind="caption"))
                    continue
                if (prev and prev.kind == "caption" and prev.page == page_no
                        and section_key(text) is None):
                    prev.text = f"{prev.text} {text}"  # el rótulo de la tabla siguió en otra línea
                    continue

            # Párrafo que sigue al anterior: empieza en minúscula y el anterior quedó sin cerrar.
            # Pasa al cambiar de página o cuando la negrita cambia a mitad de párrafo.
            if (kind == "text" and text[:1].islower() and prev and prev.kind == "text"
                    and not TERMINAL.search(prev.text)):
                prev.text = _join_lines([prev.text, text])
                if prev.page != page_no:
                    para += 1  # en esta página es un bloque visible: el siguiente párrafo es el 2
                continue

            if kind != "heading":
                para += 1  # los títulos no cuentan: "párrafo 2" es el segundo bloque de contenido
            paragraphs.append(Paragraph(page=page_no, para=0 if kind == "heading" else para,
                                        text=text, kind=kind, level=level))
    return paragraphs
