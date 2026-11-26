"""Generación de embeddings."""
from app import config


def embed(texts: list[str]) -> list[list[float]]:
    # TODO: conectar con el proveedor de embeddings (config.EMBEDDING_MODEL)
    raise NotImplementedError
