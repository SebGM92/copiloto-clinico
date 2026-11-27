"""RUNs de prueba calculados a mano con módulo 11; no corresponden a personas reales conocidas."""
import pytest

from app.guard import find_patient_data, run_is_valid


@pytest.mark.parametrize("run", ["11.111.111-1", "11111111-1", "111111111", "12.345.678-5", "12345678-5",
                                 "1.000.005-K", "1.000.005-k"])
def test_valid_runs(run):
    assert run_is_valid(run)


@pytest.mark.parametrize("run", ["11.111.111-2", "12.345.678-9", "1.000.005-1"])
def test_wrong_check_digit(run):
    assert not run_is_valid(run)


@pytest.mark.parametrize("question", [
    "Paciente RUN 12.345.678-5 con HbA1c de 9%, ¿inicio insulina?",
    "¿qué hago con el 12345678-5? tiene depresión",
    "rut 1.000.005-K, embarazada, ¿fluoxetina?",
])
def test_question_with_run_is_blocked(question):
    assert "RUN" in find_patient_data(question)


@pytest.mark.parametrize("question", [
    "¿Cuál es la meta de HbA1c en un adulto mayor frágil?",
    "Metformina 850 mg cada 12 horas, ¿se ajusta con VFG de 40?",
    "Folio 12.345.678-9 de la interconsulta",   # parece un RUN, pero el dígito verificador no calza
    "Llamar al 22 574 0100",
])
def test_clinical_questions_pass(question):
    assert find_patient_data(question) is None


def test_long_pasted_record_is_blocked():
    assert "demasiado larga" in find_patient_data("a" * 2001)
    assert find_patient_data("a" * 2000) is None
