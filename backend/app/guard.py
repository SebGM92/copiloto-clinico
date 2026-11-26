"""Filtros de entrada: decide si una consulta está dentro del alcance."""
from dataclasses import dataclass


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""


def check(query: str) -> GuardResult:
    if not query.strip():
        return GuardResult(False, "Consulta vacía")
    # TODO: reglas de alcance clínico, datos personales, etc.
    return GuardResult(True)
