from app.acronyms import expand
from app.ingest.chunker import chunk_paragraphs
from app.ingest.pdf_parser import Paragraph


def P(text, kind="text", level=0, page=1, para=1):
    return Paragraph(page=page, para=para, text=text, kind=kind, level=level)


def test_section_path_and_strength_glued():
    paras = [
        P("2. Recomendaciones", "heading", 1),
        P("2.1 Tratamiento farmacológico", "heading", 2),
        P("Se recomienda iniciar tratamiento farmacológico." + "x" * 40),
        P("Recomendación fuerte, certeza de la evidencia moderada."),
        P("Se sugiere terapia combinada."),
    ]
    chunks = chunk_paragraphs(paras, max_chars=60)
    assert chunks[0].section == "2. Recomendaciones > 2.1 Tratamiento farmacológico"
    assert "Recomendación fuerte" in chunks[0].text      # la fuerza no se separa
    assert chunks[1].text == "Se sugiere terapia combinada."


def test_table_own_chunk_and_heading_resets_path():
    paras = [
        P("2. Recomendaciones", "heading", 1),
        P("Texto antes."),
        P("| a | b |\n|---|---|", "table"),
        P("Texto después."),
        P("3. Seguimiento", "heading", 1),
        P("Controlar cada tres meses."),
    ]
    chunks = chunk_paragraphs(paras)
    assert [c.text for c in chunks] == ["Texto antes.", "| a | b |\n|---|---|", "Texto después.", "Controlar cada tres meses."]
    assert chunks[-1].section == "3. Seguimiento"


def test_expand_acronym():
    assert "hipertensión arterial" in expand("tratamiento de HTA")
