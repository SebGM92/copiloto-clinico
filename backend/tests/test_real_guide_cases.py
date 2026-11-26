"""Casos encontrados al procesar la guía real de DM2 (MINSAL 2016-2017).

Cada test reproduce el caso con un PDF FICTICIO mínimo hecho con reportlab,
así no dependemos de descargar la guía real para correr los tests.
"""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ingest.chunker import STRENGTH, chunk_paragraphs
from app.ingest.pdf_parser import Paragraph, parse_pdf

W, H = A4
X = 70
BODY = ("Texto ficticio de prueba para el parser de guías clínicas, con la extensión de un párrafo "
        "normal de cuerpo.")


def build(tmp_path, *pages):
    """Crea un PDF con una función de dibujo por página y devuelve sus párrafos."""
    path = tmp_path / "ficticio.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    for draw in pages:
        draw(c)
        c.showPage()
    c.save()
    return parse_pdf(str(path))


def lines(c, y, texts, font="Helvetica", size=10, gap=12):
    c.setFont(font, size)
    for t in texts:
        c.drawString(X, y, t)
        y -= 13
    return y - gap


def heading(c, y, text, size=14):
    c.setFont("Helvetica-Bold", size)
    c.drawString(X, y, text)
    return y - 24


# 1 ─ Encabezado vertical en el margen lateral ────────────────────────────────
def test_vertical_running_header_in_side_margin_is_removed(tmp_path):
    def page(c):
        c.saveState()
        c.translate(25, 200)
        c.rotate(90)
        c.setFont("Helvetica", 8)
        c.drawString(0, 0, "GUÍA FICTICIA DE PRUEBA TRATAMIENTO")
        c.restoreState()
        lines(c, H - 100, [BODY[:90], BODY[90:]])

    ps = build(tmp_path, page, page, page)
    assert not any("GUÍA FICTICIA" in p.text for p in ps)
    assert [(p.page, p.para) for p in ps] == [(1, 1), (2, 1), (3, 1)]


# 2 ─ Fuerza de la recomendación en negrita, detectada como título ────────────
def test_bold_strength_lines_are_content_not_headings(tmp_path):
    def page(c):
        y = heading(c, H - 100, "RECOMENDACIÓN", 11)
        y = lines(c, y, ["Se recomienda el uso del fármaco ficticio A comparado con el fármaco",
                         "ficticio B en personas adultas de este documento de prueba."])
        y = lines(c, y, ["Certeza de la evidencia: Condicional a favor del fármaco ficticio A"], "Helvetica-Bold")
        y = lines(c, y, ["Calidad de la evidencia: Baja"], "Helvetica-Bold")
        lines(c, y, [BODY[:90], BODY[90:]] * 3)

    ps = build(tmp_path, page)
    strengths = [p for p in ps if STRENGTH.match(p.text)]
    assert len(strengths) == 2 and all(p.kind == "text" for p in strengths)
    rec = next(c for c in chunk_paragraphs(ps, max_chars=120) if "fármaco ficticio A comparado" in c.text)
    assert "Certeza de la evidencia" in rec.text and "Calidad de la evidencia: Baja" in rec.text


# 3 ─ Párrafo (y palabra) que continúa en la página siguiente ─────────────────
def test_paragraph_continuing_on_next_page_is_merged(tmp_path):
    def page1(c):
        lines(c, 120, ["Los estudios ficticios mostraron una disminución del peso con el uso de Inhibi-"])

    def page2(c):
        y = lines(c, H - 100, ["dores ficticios en comparación con el grupo control de prueba."])
        lines(c, y, [BODY[:90], BODY[90:]])

    ps = build(tmp_path, page1, page2)
    first = ps[0]
    assert (first.page, first.para) == (1, 1)
    assert "uso de Inhibidores ficticios en comparación" in first.text
    # En la página 2 el trozo continuado es el bloque 1 que ve el médico: el siguiente es el párrafo 2
    assert (ps[1].page, ps[1].para) == (2, 2)
    assert ps[1].text.startswith("Texto ficticio")


# 4 ─ Cambio de negrita a mitad de párrafo ────────────────────────────────────
def test_bold_change_mid_paragraph_does_not_split_it(tmp_path):
    def page(c):
        y = H - 100
        c.setFont("Helvetica", 10)
        first = "En caso de indicar el fármaco ficticio, "
        c.drawString(X, y, first)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(X + c.stringWidth(first, "Helvetica", 10), y, "se recomienda usar la dosis ficticia com-")
        c.drawString(X, y - 13, "parada con la dosis de referencia en adultos de este documento de prueba.")
        lines(c, y - 40, [BODY[:90], BODY[90:]] * 3)

    ps = build(tmp_path, page)
    rec = next(p for p in ps if "fármaco ficticio" in p.text)
    assert "dosis ficticia comparada con la dosis de referencia" in rec.text
    assert not any(p.text.startswith("parada") for p in ps)


# 5 ─ Flujograma dibujado con texto vectorial (no es una imagen) ──────────────
def test_vector_flowchart_page_is_discarded(tmp_path):
    labels = ["¿Cumple meta?", "Sí", "No", "Continuar", "Reevaluar", "Fármaco A", "Fármaco B", "Referir"]

    def text_page(c):
        lines(c, H - 100, [BODY[:90], BODY[90:]] * 4)

    def flowchart(c):
        c.setFont("Helvetica", 9)
        for i in range(24):
            # cajas a alturas distintas, como en el algoritmo real (si comparten línea base, PyMuPDF las une)
            x, y = 70 + (i % 4) * 120, H - 120 - (i // 4) * 90 - (i % 4) * 20
            c.rect(x, y - 6, 100, 24)
            c.drawString(x + 6, y + 2, labels[i % len(labels)])

    ps = build(tmp_path, text_page, flowchart)
    assert {p.page for p in ps} == {1}
    assert not any(p.text in labels for p in ps)


def test_page_with_short_list_items_is_not_a_flowchart(tmp_path):
    def page(c):
        y = H - 100
        for i in range(25):
            y = lines(c, y, [f"• Base de datos ficticia {i}"], gap=4)

    ps = build(tmp_path, page)
    assert len(ps) == 25


# 6 ─ Palabras cortadas con guion dentro de celdas de tabla ───────────────────
def test_hyphenated_words_inside_table_cells_are_joined(tmp_path):
    def page(c):
        lines(c, H - 80, [BODY[:90], BODY[90:]])
        top, cw, rh = H - 140, 160, 30
        cells = [["DESENLACE", "N° DE ESTU-|DIOS"], ["Hipoglicemia", "uso de hipoglice-|miantes ficticios"]]
        c.setFont("Helvetica", 9)
        for i, row in enumerate(cells):
            for j, cell in enumerate(row):
                for k, part in enumerate(cell.split("|")):
                    c.drawString(X + j * cw + 4, top - i * rh - 11 - k * 10, part)
        for i in range(3):
            c.line(X, top - i * rh, X + 2 * cw, top - i * rh)
        for j in range(3):
            c.line(X + j * cw, top, X + j * cw, top - 2 * rh)

    table = next(p for p in build(tmp_path, page) if p.kind == "table")
    assert "N° DE ESTUDIOS" in table.text
    assert "uso de hipoglicemiantes ficticios" in table.text


# 7 ─ Títulos del mismo tamaño: "Recomendación N" + su pregunta, bajo "3.1 …" ──
def test_same_size_headings_build_the_right_section_path():
    def h(text, level=2):
        return Paragraph(page=1, para=0, text=text, kind="heading", level=level)

    def t(text):
        return Paragraph(page=1, para=1, text=text, kind="text")

    paras = [
        h("3. RECOMENDACIONES", 1),
        h("3.1 PRIMERA LÍNEA DE TRATAMIENTO"), t("Introducción ficticia."),
        h("Recomendación 1"), h("¿Debería usarse el fármaco ficticio A?"), t("Se recomienda A."),
        h("3.2 SEGUNDA LÍNEA DE TRATAMIENTO"), h("Recomendación 2"), h("¿Y el fármaco B?"), t("Se recomienda B."),
    ]
    sections = {c.text: c.section for c in chunk_paragraphs(paras)}
    assert sections["Se recomienda A."] == (
        "3. RECOMENDACIONES > 3.1 PRIMERA LÍNEA DE TRATAMIENTO > "
        "Recomendación 1 ¿Debería usarse el fármaco ficticio A?")
    assert sections["Se recomienda B."] == (
        "3. RECOMENDACIONES > 3.2 SEGUNDA LÍNEA DE TRATAMIENTO > Recomendación 2 ¿Y el fármaco B?")


# 8 ─ Ítems de lista en negrita, detectados como título ───────────────────────
def test_bold_list_items_are_content_not_headings(tmp_path):
    def page(c):
        y = lines(c, H - 100, ["Se recomienda iniciar el fármaco ficticio en las siguientes situaciones:"])
        y = lines(c, y, ["• Debut inestable:"], "Helvetica-Bold")
        y = lines(c, y, ["Síntomas ficticios y glicemia ficticia elevada."])
        y = lines(c, y, ["• Durante la evolución de la enfermedad:"], "Helvetica-Bold")
        lines(c, y, [BODY[:90], BODY[90:]] * 3)

    ps = build(tmp_path, page)
    assert not any(p.kind == "heading" for p in ps)
    first = chunk_paragraphs(ps)[0]
    assert "• Debut inestable:" in first.text and "• Durante la evolución" in first.text


# 9 ─ Viñeta sola en su propia línea ──────────────────────────────────────────
def test_lone_bullet_glyph_is_attached_to_its_item(tmp_path):
    def page(c):
        y = lines(c, H - 100, ["Criterios ficticios para iniciar el tratamiento de prueba:"])
        c.setFont("Helvetica", 11)
        c.drawString(X, y + 3, "−−")  # la viñeta va en otra línea base que el texto, como en la guía real
        lines(c, y - 4, ["Síntomas ficticios y glicemia ficticia elevada."])
        lines(c, y - 60, [BODY[:90], BODY[90:]] * 3)

    ps = build(tmp_path, page)
    assert not any(not any(ch.isalnum() for ch in p.text) for p in ps)
    assert any(p.text == "– Síntomas ficticios y glicemia ficticia elevada." for p in ps)


# ═══ Casos encontrados en la guía de Depresión (MINSAL 2013) ═════════════════

def _h(text, level, page=1):
    return Paragraph(page=page, para=0, text=text, kind="heading", level=level)


def _t(text, page=1):
    return Paragraph(page=page, para=1, text=text, kind="text")


def _sections(paras):
    return {c.text: c.section for c in chunk_paragraphs(paras)}


# 10 ─ Títulos de portada encabezando todas las secciones ─────────────────────
def test_cover_titles_bigger_than_chapters_stay_out_of_the_section_path():
    paras = [
        _h("Depresión", 1), _h("en personas de 15 años y más", 3), _t("Portada ficticia."),
        _h("RECOMENDACIONES CLAVE", 6, page=11), _t("Recomendación clave ficticia.", page=11),
        _h("1. INTRODUCCIÓN", 6, page=13), _t("Introducción ficticia.", page=13),
    ]
    s = _sections(paras)
    assert s["Recomendación clave ficticia."] == "RECOMENDACIONES CLAVE"
    assert s["Introducción ficticia."] == "1. INTRODUCCIÓN"


# 11 ─ Índice de la guía guardado como contenido ──────────────────────────────
def test_table_of_contents_is_not_content(tmp_path):
    def toc_page(c):
        y = heading(c, H - 100, "ÍNDICE")
        for entry, page in [("1. INTRODUCCIÓN", 5), ("1.1. Descripción del problema", 5),
                            ("2. ALCANCE DE LA GUÍA", 9), ("3. RECOMENDACIONES", 12)]:
            y = lines(c, y, [f"{entry}{'.' * 60}{page}"], gap=2)

    def toc_table_page(c):
        top, cw, rh = H - 120, 200, 18
        rows = [["AUTORES", "4"], ["1. INTRODUCCIÓN", "8"], ["2. MÉTODOS", "11"], ["3. RECOMENDACIONES", "14"]]
        c.setFont("Helvetica", 10)
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                c.drawString(X + j * cw + 4, top - i * rh - 13, cell)
        for i in range(len(rows) + 1):
            c.line(X, top - i * rh, X + 2 * cw, top - i * rh)
        for j in range(3):
            c.line(X + j * cw, top, X + j * cw, top - len(rows) * rh)

    def body(c):
        y = heading(c, H - 100, "1. INTRODUCCIÓN")
        lines(c, y, [BODY[:90], BODY[90:]] * 3)

    ps = build(tmp_path, toc_page, toc_table_page, body)
    assert {p.page for p in ps} == {3}  # nada de las páginas de índice (líneas con puntos ni tabla)
    assert not any("ÍNDICE" in p.text or "AUTORES" in p.text for p in ps)
    assert chunk_paragraphs(ps)[0].section == "1. INTRODUCCIÓN"


def test_numeric_table_that_is_not_an_index_is_kept(tmp_path):
    def page(c):
        lines(c, H - 80, [BODY[:90], BODY[90:]])
        top, cw, rh = H - 140, 150, 18
        rows = [["Edad", "Casos"], ["15-24", "320"], ["25-44", "210"], ["45-64", "150"], ["65 y más", "90"]]
        c.setFont("Helvetica", 10)
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                c.drawString(X + j * cw + 4, top - i * rh - 13, cell)
        for i in range(len(rows) + 1):
            c.line(X, top - i * rh, X + 2 * cw, top - i * rh)
        for j in range(3):
            c.line(X + j * cw, top, X + j * cw, top - len(rows) * rh)

    table = next(p for p in build(tmp_path, page) if p.kind == "table")
    assert "15-24" in table.text and "320" in table.text


# 12 ─ Rótulo de tabla ("Tabla Nº 1: …") tomado como título de sección ─────────
def test_table_caption_travels_with_its_table(tmp_path):
    def page(c):
        y = heading(c, H - 100, "1. INTRODUCCIÓN")
        y = lines(c, y, [BODY[:90], BODY[90:]])
        y = heading(c, y, "Tabla Nº 1: Prevalencia ficticia de depresión en Chile, según", 10)
        y = heading(c, y + 10, "DSM ficticio (entrevista estructurada)", 10)
        top, cw, rh = y, 150, 18
        rows = [["Grupo", "Prevalencia"], ["Hombres", "5,5 %"], ["Mujeres", "11,2 %"]]
        c.setFont("Helvetica", 10)
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                c.drawString(X + j * cw + 4, top - i * rh - 13, cell)
        for i in range(len(rows) + 1):
            c.line(X, top - i * rh, X + 2 * cw, top - i * rh)
        for j in range(3):
            c.line(X + j * cw, top, X + j * cw, top - len(rows) * rh)
        lines(c, top - len(rows) * rh - 25, ["Fuente: encuesta ficticia. " + BODY])

    ps = build(tmp_path, page)
    caption = next(p for p in ps if p.kind == "caption")
    assert caption.text == ("Tabla Nº 1: Prevalencia ficticia de depresión en Chile, según "
                            "DSM ficticio (entrevista estructurada)")
    chunks = chunk_paragraphs(ps)
    table_chunk = next(c for c in chunks if any(p.kind == "table" for p in c.paragraphs))
    assert [p.kind for p in table_chunk.paragraphs] == ["caption", "table"]
    assert all(c.section == "1. INTRODUCCIÓN" for c in chunks)  # el rótulo no queda en la ruta


def test_caption_without_table_stays_as_text():
    paras = [_h("1. INTRODUCCIÓN", 1), Paragraph(1, 0, "Figura 2: Algoritmo ficticio", "caption"),
             _t("Texto después de la figura.")]
    (chunk,) = chunk_paragraphs(paras)
    assert chunk.text == "Figura 2: Algoritmo ficticio\n\nTexto después de la figura."


# 13 ─ Llamadas a nota al pie pegadas al título ("Presentación clínica¹") ──────
def test_footnote_markers_are_removed_from_headings_but_not_from_text(tmp_path):
    def page(c):
        t = c.beginText(X, H - 100)
        t.setFont("Helvetica-Bold", 14)
        t.textOut("1.3.1. Presentación clínica")
        t.setFont("Helvetica-Bold", 7)
        t.setRise(3)  # elevación pequeña, como en la guía real: PyMuPDF lo deja en la línea y lo marca superíndice
        t.textOut("1")
        t.setRise(0)
        c.drawText(t)
        t = c.beginText(X, H - 130)
        t.setFont("Helvetica", 10)
        t.textOut("Pacientes ficticios con IMC sobre 30 kg/m")
        t.setFont("Helvetica", 6)
        t.setRise(3)
        t.textOut("2")
        t.setRise(0)
        t.setFont("Helvetica", 10)
        t.textOut(" en este documento de prueba.")
        c.drawText(t)
        lines(c, H - 160, [BODY[:90], BODY[90:]] * 3)

    ps = build(tmp_path, page)
    assert next(p for p in ps if p.kind == "heading").text == "1.3.1. Presentación clínica"
    assert any("kg/m2" in p.text for p in ps if p.kind == "text")


# 14 ─ La numeración define la jerarquía, no el tamaño de letra ───────────────
def test_section_numbering_defines_the_hierarchy():
    paras = [
        _h("1. INTRODUCCIÓN", 6),
        _h("1.1. Descripción del problema", 9), _t("A."),
        _h("Epidemiología ficticia", 8), _t("B."),  # sin número y más grande que 1.1: cuelga de 1.1 igual
        _h("5. RECOMENDACIONES", 6), _h("5.3. Tratamiento", 9), _h("5.3.2. Síntesis de Evidencia", 8),
        _h("1. Fármaco versus Placebo", 8), _t("C."),  # numeración de lista dentro de 5.3.2: no es el capítulo 1
        _h("ANEXO 1. Glosario ficticio", 6), _t("D."),
        _h("REFERENCIAS", 6), _t("E."),
    ]
    s = _sections(paras)
    assert s["A."] == "1. INTRODUCCIÓN > 1.1. Descripción del problema"
    assert s["B."] == "1. INTRODUCCIÓN > 1.1. Descripción del problema > Epidemiología ficticia"
    assert s["C."] == ("5. RECOMENDACIONES > 5.3. Tratamiento > 5.3.2. Síntesis de Evidencia > "
                       "1. Fármaco versus Placebo")
    assert s["D."] == "ANEXO 1. Glosario ficticio"
    assert s["E."] == "REFERENCIAS"
