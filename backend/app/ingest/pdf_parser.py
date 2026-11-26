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
    kind: str        # "heading" | "text" | "table"
    level: int = 0   # nivel del título (1 = más grande); 0 si no es título


MARGIN = 0.08  # 8 % superior e inferior de la página: zona de encabezados y pies


def _join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if text.endswith("-") and line[:1].islower():
            text = text[:-1] + line          # "hiperten-" + "sión" -> "hipertensión"
        else:
            text = f"{text} {line}" if text else line
    return re.sub(r"\s+", " ", text).strip()


def _signature(text: str) -> str:
    """Firma para detectar encabezados repetidos: sin números ni mayúsculas."""
    return re.sub(r"\d+", "#", text.lower()).strip()


def _table_markdown(rows: list[list[str | None]]) -> str:
    clean = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in rows]
    header, body = clean[0], clean[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def _line_style(line: dict) -> tuple[float, bool]:
    spans = [s for s in line["spans"] if s["text"].strip()]
    size = round(max(s["size"] for s in spans), 1)
    bold = all(s["flags"] & 16 for s in spans)  # flag 16 = negrita
    return size, bold


def _raw_blocks(doc: pymupdf.Document) -> list[list[dict]]:
    pages = []
    for page in doc:
        height = page.rect.height
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
                if runs and runs[-1]["style"] == style:
                    runs[-1]["lines"].append(text)
                    runs[-1]["y1"] = line["bbox"][3]
                else:
                    runs.append({"style": style, "lines": [text], "y0": line["bbox"][1], "y1": line["bbox"][3]})
            for run in runs:
                blocks.append({
                    "y0": run["y0"], "y1": run["y1"], "height": height,
                    "text": _join_lines(run["lines"]),
                    "size": run["style"][0], "bold": run["style"][1], "kind": "text",
                })
        for t in tables:
            # get_textbox por celda conserva los espacios mejor que t.extract()
            rows = [[page.get_textbox(cell) if cell else "" for cell in row.cells] for row in t.rows]
            blocks.append({
                "y0": t.bbox[1], "y1": t.bbox[3], "height": height,
                "text": _table_markdown(rows), "size": 0, "bold": False, "kind": "table",
            })
        pages.append(sorted(blocks, key=lambda b: b["y0"]))
    return pages


def _repeated_margin_text(pages: list[list[dict]]) -> set[str]:
    """Textos en los márgenes que se repiten en al menos la mitad de las páginas."""
    if len(pages) < 3:
        return set()
    counts = Counter()
    for blocks in pages:
        seen = {
            _signature(b["text"]) for b in blocks
            if b["y1"] < b["height"] * MARGIN or b["y0"] > b["height"] * (1 - MARGIN)
        }
        counts.update(seen)
    return {sig for sig, n in counts.items() if n >= len(pages) / 2}


def parse_pdf(path: str) -> list[Paragraph]:
    doc = pymupdf.open(path)
    pages = _raw_blocks(doc)
    repeated = _repeated_margin_text(pages)

    text_sizes = [b["size"] for blocks in pages for b in blocks if b["kind"] == "text" for _ in range(len(b["text"]))]
    body_size = statistics.median(text_sizes) if text_sizes else 10
    heading_sizes = sorted({b["size"] for blocks in pages for b in blocks if b["size"] >= body_size + 1.5}, reverse=True)

    paragraphs = []
    for page_no, blocks in enumerate(pages, start=1):
        para = 0
        for b in blocks:
            text = b["text"]
            in_margin = b["y1"] < b["height"] * MARGIN or b["y0"] > b["height"] * (1 - MARGIN)
            if in_margin and (_signature(text) in repeated or text.strip().isdigit()):
                continue  # encabezado, pie o número de página

            kind, level = b["kind"], 0
            if kind == "text" and b["size"] in heading_sizes:
                kind, level = "heading", heading_sizes.index(b["size"]) + 1
            elif kind == "text" and b["bold"] and len(text) < 120 and not text.endswith("."):
                kind, level = "heading", len(heading_sizes) + 1

            if kind != "heading":
                para += 1  # los títulos no cuentan: "párrafo 2" es el segundo bloque de contenido
            paragraphs.append(Paragraph(page=page_no, para=0 if kind == "heading" else para,
                                        text=text, kind=kind, level=level))
    return paragraphs
