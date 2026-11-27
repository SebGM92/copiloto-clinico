"""Siglas frecuentes en las guías chilenas. Amplía esta lista con las de tu corpus."""
import re

ACRONYMS = {
    "HTA": "hipertensión arterial",
    "DM": "diabetes mellitus",
    "DM1": "diabetes mellitus tipo 1",
    "DM2": "diabetes mellitus tipo 2",
    "HBA1C": "hemoglobina glicosilada",
    "ERC": "enfermedad renal crónica",
    "VFG": "velocidad de filtración glomerular",
    "IAM": "infarto agudo al miocardio",
    "ACV": "accidente cerebrovascular",
    "EPOC": "enfermedad pulmonar obstructiva crónica",
    "NAC": "neumonía adquirida en la comunidad",
    "IECA": "inhibidores de la enzima convertidora de angiotensina",
    "ARA2": "antagonistas del receptor de angiotensina II",
    "PA": "presión arterial",
    "IMC": "índice de masa corporal",
    "APS": "atención primaria de salud",
    # Del corpus actual (guías DM2 y Depresión): siglas que la guía también escribe en forma larga.
    # Significados del glosario de la guía de Depresión (Anexo 1) o del propio texto.
    "ECV": "enfermedades cardiovasculares",
    "GLP": "péptido similar al glucagón",
    # La guía DM2 escribe "Inhibidores de DPP4" y a veces "iDPP4"; para la búsqueda léxica
    # "idpp4" y "dpp4" son lexemas distintos (evaluación: la pregunta dm2-04 se perdía en la híbrida)
    "IDPP4": "inhibidores de DPP4",
    "ISGLT2": "inhibidores de SGLT2",
    "ISRS": "inhibidores selectivos de la recaptación de serotonina",
    "ATC": "antidepresivos tricíclicos",
    "IMAO": "inhibidores de la monoaminooxidasa",
    "TCC": "terapia cognitivo conductual",
    "TIP": "terapia interpersonal",
    "TEC": "terapia electroconvulsiva",
    "EPDS": "escala de depresión posparto de Edimburgo",
    "EDPS": "escala de depresión posparto de Edimburgo",
    "GHQ": "cuestionario de salud general de Goldberg",
    "CIE": "clasificación internacional de enfermedades",
    "TEPT": "trastorno de estrés post traumático",
    "TBP": "trastorno bipolar",
    "TDAH": "trastorno por déficit atencional con hiperactividad",
    "GES": "garantías explícitas en salud",
    # No se agregan a propósito:
    #   SU  (sulfonilureas): choca con el posesivo "su"; expand() no distingue mayúsculas.
    #   DPP (depresión posparto): en la guía DM2 es parte de "DPP-4" (dipeptidil peptidasa).
    #   DPP4, SGLT2, NPH, DSM: la guía nunca las escribe en forma larga; ampliarlas no ayuda a buscar.
}


def expand(question: str) -> str:
    """Agrega el significado de cada sigla encontrada: 'dosis en DM2' -> '... diabetes mellitus tipo 2'."""
    found = {w.upper() for w in re.findall(r"\b[A-Za-z]+\d?[A-Za-z]?\d?\b", question)}
    extra = [ACRONYMS[w] for w in sorted(found) if w in ACRONYMS]
    return " ".join([question, *extra])
