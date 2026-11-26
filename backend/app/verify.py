"""Verificación de que la respuesta está respaldada por las fuentes."""
from dataclasses import dataclass


@dataclass
class VerifyResult:
    grounded: bool
    notes: str = ""


def verify(answer: str, sources: list[str]) -> VerifyResult:
    # TODO: comprobar citas y respaldo en las fuentes
    return VerifyResult(grounded=bool(sources))
