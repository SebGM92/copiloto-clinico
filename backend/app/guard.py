"""Bloquea preguntas con datos de pacientes antes de enviarlas a un servicio externo."""
import re

RUN_PATTERN = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK]\b")


def run_is_valid(run: str) -> bool:
    """Dígito verificador con módulo 11 (el mismo validador del proyecto 1)."""
    limpio = run.replace(".", "").replace("-", "").upper()
    cuerpo, dv = limpio[:-1], limpio[-1:]
    if not cuerpo.isdigit():
        return False
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return dv == {11: "0", 10: "K"}.get(resto, str(resto))


def find_patient_data(question: str) -> str | None:
    """Devuelve un motivo de bloqueo, o None si la pregunta se puede procesar."""
    if any(run_is_valid(m) for m in RUN_PATTERN.findall(question)):
        return "La pregunta contiene un RUN. No incluyas datos que identifiquen a un paciente."
    if len(question) > 2000:
        return "La pregunta es demasiado larga. Pregunta por un tema clínico, no pegues fichas."
    return None
