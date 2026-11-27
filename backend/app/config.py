import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rag:rag@localhost:5433/rag")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

TOP_K = int(os.getenv("TOP_K", "8"))
# Similitud coseno mínima del mejor fragmento para llamar al LLM.
# Calibrado en la Fase 8 con el set dorado (bge-m3): preguntas con respuesta >= 0.586,
# fuera de tema 0.431-0.510. Las trampas (0.60-0.66) llegan al modelo, que se abstiene.
MIN_SIMILARITY = float(os.getenv("MIN_SIMILARITY", "0.55"))
