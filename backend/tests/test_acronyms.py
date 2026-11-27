from app.acronyms import ACRONYMS, expand


def test_expands_acronyms_keeping_the_question():
    out = expand("¿Meta de HbA1c en DM2?")
    assert out.startswith("¿Meta de HbA1c en DM2?")
    assert "hemoglobina glicosilada" in out and "diabetes mellitus tipo 2" in out


def test_lowercase_acronyms_also_expand():
    assert "hipertensión arterial" in expand("tratamiento de la hta")


def test_hyphenated_forms_expand():
    assert "péptido similar al glucagón" in expand("análogos de GLP-1")


def test_corpus_acronyms():
    assert "recaptación de serotonina" in expand("¿Qué ISRS usar en adolescentes?")


def test_no_expansion_without_acronyms():
    assert expand("dosis máxima de metformina") == "dosis máxima de metformina"


def test_common_spanish_words_do_not_expand():
    # "su" no está en la lista a propósito: si estuviera, "ajustar su dosis" sumaría "sulfonilureas"
    assert "SU" not in ACRONYMS
    assert expand("ajustar su dosis según la función renal") == "ajustar su dosis según la función renal"
