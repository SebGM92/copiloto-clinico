"""Genera una guía clínica FICTICIA en PDF para los tests del parser y el chunker.

Uso: python -m tests.make_fake_guide [salida.pdf]
"""
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

W, H = A4
LEFT = 60
HEADER = "Guía Clínica Ficticia de Hipertensión - DOCUMENTO FICTICIO, NO USAR EN PACIENTES"
TOTAL_PAGES = 3

LOSARTAN = ("Se recomienda iniciar losartán 50 mg al día en adultos con hipertensión arterial "
            "y diabetes mellitus tipo 2.")


def _frame(c: canvas.Canvas, n: int) -> None:
    """Encabezado y pie repetidos en todas las páginas, con número de página."""
    c.setFont("Helvetica", 8)
    c.drawString(LEFT, H - 30, HEADER)
    c.drawString(LEFT, 30, f"Ministerio Ficticio de Salud - Página {n} de {TOTAL_PAGES}")
    c.drawRightString(W - LEFT, 30, str(n))


def _heading(c: canvas.Canvas, y: float, text: str, level: int) -> float:
    c.setFont("Helvetica-Bold", 16 if level == 1 else 13)
    c.drawString(LEFT, y, text)
    return y - 28


def _para(c: canvas.Canvas, y: float, lines: list[str], font: str = "Helvetica") -> float:
    c.setFont(font, 10)
    for line in lines:
        c.drawString(LEFT, y, line)
        y -= 13
    return y - 12  # separación entre párrafos: cada uno queda en su propio bloque


def _table(c: canvas.Canvas, y: float, rows: list[list[str]]) -> float:
    col_w, row_h = 150, 18
    c.setFont("Helvetica", 10)
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c.drawString(LEFT + j * col_w + 4, y - i * row_h - 13, cell)
    for i in range(len(rows) + 1):
        c.line(LEFT, y - i * row_h, LEFT + len(rows[0]) * col_w, y - i * row_h)
    for j in range(len(rows[0]) + 1):
        c.line(LEFT + j * col_w, y, LEFT + j * col_w, y - len(rows) * row_h)
    return y - len(rows) * row_h - 25


def make_fake_guide(path: str | Path) -> Path:
    path = Path(path)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Guía clínica FICTICIA - solo para tests")

    # Página 1
    _frame(c, 1)
    y = _heading(c, H - 100, "1. Tratamiento farmacológico", 1)
    y = _para(c, y, ["DOCUMENTO FICTICIO generado para pruebas automáticas. Su contenido no es una",
                     "recomendación clínica real y no debe usarse para atender pacientes."])
    y = _heading(c, y, "1.1 Fármacos de primera línea", 2)
    y = _para(c, y, [LOSARTAN[:83], LOSARTAN[83:].strip()])
    y = _para(c, y, ["Recomendación fuerte, certeza de la evidencia moderada."])
    y = _para(c, y, ["Se sugiere agregar amlodipino 5 mg al día si no se alcanza la meta de presión",
                     "arterial tras tres meses de tratamiento con un solo fármaco."])
    y = _para(c, y, ["Recomendación condicional, certeza de la evidencia baja."])
    c.showPage()

    # Página 2
    _frame(c, 2)
    y = _heading(c, H - 100, "1.2 Dosis habituales", 2)
    y = _para(c, y, ["La siguiente tabla resume las dosis ficticias usadas en esta guía."])
    y = _table(c, y, [["Fármaco", "Dosis inicial", "Dosis máxima"],
                      ["Losartán", "50 mg", "100 mg"],
                      ["Amlodipino", "5 mg", "10 mg"]])
    y = _para(c, y, ["Ajustar la dosis según la función renal del paciente."])
    c.showPage()

    # Página 3
    _frame(c, 3)
    y = _heading(c, H - 100, "2. Seguimiento", 1)
    y = _para(c, y, ["Se recomienda controlar la presión arterial cada tres meses durante el primer",
                     "año de tratamiento y luego cada seis meses si está controlada."])
    y = _para(c, y, ["Grado de recomendación B."])
    c.showPage()

    c.save()
    return path


if __name__ == "__main__":
    out = make_fake_guide(sys.argv[1] if len(sys.argv) > 1 else "guia_ficticia.pdf")
    print(f"PDF ficticio: {out}")
