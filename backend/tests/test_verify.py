from app.llm import AnswerBlock, Citation
from app.retrieval import RetrievedChunk
from app.verify import ABSTENTION, numbers, verify

LOSARTAN = "Se recomienda iniciar losartán 50 mg al día."
CHUNK = RetrievedChunk(
    id=7, section="1.1 Fármacos", page_start=4, page_end=4,
    paragraphs=[{"page": 4, "para": 2, "text": LOSARTAN, "kind": "text"},
                {"page": 4, "para": 3, "text": "Meta de HbA1c 7,5 %.", "kind": "text"}],
    content="", slug="g", title="Guía ficticia", year=2024, source_url="https://x/g.pdf",
    similarity=0.7, semantic_rank=1, keyword_rank=1, score=0.03,
)


def cite(start=0, end=1, index=0, text=LOSARTAN):
    return Citation(index, start, end, text)


def test_numbers_normalize_decimal_comma_and_skip_list_markers():
    assert numbers("1. Meta de 7,5 %\n2) dosis 50 mg") == {"7.5", "50"}


def test_cited_numbers_are_verified_with_page_and_paragraph():
    v = verify([AnswerBlock("Losartán 50 mg al día.", [cite()])], [CHUNK])
    assert v.status == "verified" and v.problems == []
    (ref,) = v.refs
    assert ref.n == 1 and ref.url == "https://x/g.pdf#page=4"
    assert ref.paragraphs == [{"page": 4, "para": 2, "kind": "text"}]


def test_decimal_comma_matches_decimal_point():
    v = verify([AnswerBlock("La meta es 7.5 %.", [cite(1, 2, text="Meta de HbA1c 7,5 %.")])], [CHUNK])
    assert v.status == "verified"


def test_abstention_phrase_or_no_citations_is_abstained():
    assert verify([AnswerBlock(ABSTENTION + " Cubren DM2 y depresión.")], [CHUNK]).status == "abstained"
    assert verify([AnswerBlock("No encontré nada.")], [CHUNK]).status == "abstained"


def test_wrong_dose_is_retracted():
    # "100 mg" citando un párrafo que dice "50 mg"
    v = verify([AnswerBlock("Losartán 100 mg al día.", [cite()])], [CHUNK])
    assert v.status == "retracted" and "100" in v.problems[0]


def test_number_without_citation_is_retracted():
    blocks = [AnswerBlock("Losartán al día.", [cite()]), AnswerBlock("Máximo 200 mg.")]
    v = verify(blocks, [CHUNK])
    assert v.status == "retracted" and "sin cita" in v.problems[0]


def test_text_without_numbers_and_without_citation_is_fine():
    blocks = [AnswerBlock("Según la guía:\n- "), AnswerBlock("Losartán 50 mg.", [cite()])]
    assert verify(blocks, [CHUNK]).status == "verified"


def test_citation_to_missing_source_is_retracted():
    v = verify([AnswerBlock("Losartán.", [cite(index=5)])], [CHUNK])
    assert v.status == "retracted" and "no fue entregada" in v.problems[0]


def test_citation_text_mismatch_is_retracted():
    v = verify([AnswerBlock("Losartán.", [cite(text="Otro texto.")])], [CHUNK])
    assert v.status == "retracted" and "no coincide" in v.problems[0]


def test_known_false_positive_paraphrased_number():
    # Falso positivo aceptado: preferimos retirar una respuesta correcta a dejar pasar una dosis inventada
    chunk = RetrievedChunk(**{**CHUNK.__dict__, "paragraphs": [{"page": 1, "para": 1, "text": "Control trimestral.", "kind": "text"}]})
    v = verify([AnswerBlock("Control cada 3 meses.", [cite(text="Control trimestral.")])], [chunk])
    assert v.status == "retracted"


# Ajuste tras probar con respuestas reales: las frases de introducción nombran la guía y sus partes
DM2 = RetrievedChunk(**{**CHUNK.__dict__, "title": "Guía de Práctica Clínica GES Diabetes Mellitus tipo 2", "year": 2017})
DEP = RetrievedChunk(**{**CHUNK.__dict__, "title": "Guía Clínica GES Depresión en personas de 15 años y más", "year": 2013})


def test_guide_title_and_year_in_uncited_intro_are_not_clinical_data():
    blocks = [AnswerBlock("La guía GES de Diabetes Mellitus tipo 2 (2017) indica:\n- "),
              AnswerBlock("Losartán 50 mg al día.", [cite()])]
    assert verify(blocks, [DM2]).status == "verified"
    blocks[0] = AnswerBlock("Según la Guía de Depresión en personas de 15 años y más (2013):")
    assert verify(blocks, [DEP]).status == "verified"


def test_references_to_parts_of_the_guide_are_not_clinical_data():
    blocks = [AnswerBlock("- Escala de Edimburgo (Anexo 6), ver Tabla Nº 1 y Recomendación 3:"),
              AnswerBlock("Losartán 50 mg al día.", [cite()])]
    assert verify(blocks, [CHUNK]).status == "verified"


def test_title_numbers_only_count_with_their_title_word():
    # "tipo 2" está en el título, pero "2 comprimidos" es un dato clínico sin cita
    blocks = [AnswerBlock("Losartán al día.", [cite()]), AnswerBlock("Tomar 2 comprimidos.")]
    assert verify(blocks, [DM2]).status == "retracted"


def test_year_only_counts_as_whole_number():
    blocks = [AnswerBlock("Losartán al día.", [cite()]), AnswerBlock("Dosis máxima 20170 UI.")]
    assert verify(blocks, [DM2]).status == "retracted"


def test_wrong_dose_is_still_retracted_with_metadata_allowances():
    v = verify([AnswerBlock("Según la guía tipo 2 (2017), losartán 100 mg.", [cite()])], [DM2])
    assert v.status == "retracted" and "100" in v.problems[0]
