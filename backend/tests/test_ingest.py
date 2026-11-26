"""Tests de ingesta con una guía FICTICIA generada con reportlab."""
import pytest

from app.ingest.chunker import STRENGTH, chunk_paragraphs
from app.ingest.pdf_parser import parse_pdf
from tests.make_fake_guide import HEADER, LOSARTAN, make_fake_guide


@pytest.fixture(scope="module")
def paragraphs(tmp_path_factory):
    pdf = make_fake_guide(tmp_path_factory.mktemp("pdf") / "guia_ficticia.pdf")
    return parse_pdf(str(pdf))


def test_losartan_is_page_1_paragraph_2(paragraphs):
    p = next(p for p in paragraphs if "losartán 50 mg" in p.text and p.kind == "text")
    assert (p.page, p.para) == (1, 2)
    assert p.text == LOSARTAN


def test_no_headers_footers_or_page_numbers(paragraphs):
    texts = [p.text for p in paragraphs]
    assert not any(HEADER in t or "Ministerio Ficticio" in t for t in texts)
    assert not any(t.strip().isdigit() for t in texts)


def test_two_heading_levels(paragraphs):
    headings = {p.text: p.level for p in paragraphs if p.kind == "heading"}
    assert headings["1. Tratamiento farmacológico"] == 1
    assert headings["1.1 Fármacos de primera línea"] == 2
    assert headings["2. Seguimiento"] == 1


def test_dose_table_as_markdown(paragraphs):
    tables = [p for p in paragraphs if p.kind == "table"]
    assert len(tables) == 1
    assert tables[0].page == 2
    assert "| Losartán | 50 mg | 100 mg |" in tables[0].text


def test_strength_is_its_own_paragraph(paragraphs):
    # Sin esto, el test del chunker no probaría nada: la fuerza debe llegar separada
    strengths = [p for p in paragraphs if STRENGTH.match(p.text)]
    assert len(strengths) == 3


def test_chunker_never_opens_with_strength(paragraphs):
    chunks = chunk_paragraphs(paragraphs, max_chars=120)
    assert len(chunks) > 3  # el límite artificial sí obliga a cortar
    for c in chunks:
        assert not STRENGTH.match(c.paragraphs[0].text), c.text
    losartan = next(c for c in chunks if LOSARTAN in c.text)
    assert "Recomendación fuerte" in losartan.text
    assert losartan.section == "1. Tratamiento farmacológico > 1.1 Fármacos de primera línea"
