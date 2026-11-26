"""Expansión de siglas clínicas para mejorar la recuperación."""
import re

ACRONYMS: dict[str, str] = {
    "HTA": "hipertensión arterial",
    "DM2": "diabetes mellitus tipo 2",
    "IAM": "infarto agudo de miocardio",
    "EPOC": "enfermedad pulmonar obstructiva crónica",
}


def expand(query: str) -> str:
    def repl(m: re.Match) -> str:
        word = m.group(0)
        full = ACRONYMS.get(word.upper())
        return f"{word} ({full})" if full else word

    return re.sub(r"\b[A-Za-z0-9]{2,6}\b", repl, query)
