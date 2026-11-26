import hashlib
import math
import re
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3Embedder:
    """bge-m3 local con sentence-transformers. Vectores normalizados de 1024 dimensiones."""

    dim = 1024

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer  # import pesado: solo si se usa

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, batch_size=16, normalize_embeddings=True)
        return vectors.tolist()


class HashingEmbedder:
    """Solo para tests: bolsa de palabras con hashing. Determinista y sin descargar modelos."""

    dim = 1024

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in re.findall(r"\w+", text.lower()):
                bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
                vec[bucket] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out
