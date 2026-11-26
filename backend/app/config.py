import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rag:rag@localhost:5433/rag")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

TOP_K = int(os.getenv("TOP_K", "8"))
# Similitud coseno mínima del mejor fragmento para llamar al LLM.
# Es un punto de partida: se calibra en la Fase 8 con preguntas fuera del corpus.
MIN_SIMILARITY = float(os.getenv("MIN_SIMILARITY", "0.45"))
