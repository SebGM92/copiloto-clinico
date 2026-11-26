"""División de texto en fragmentos para indexar."""


def chunk_text(text: str, size: int = 1000, overlap: int = 200) -> list[str]:
    if size <= overlap:
        raise ValueError("size debe ser mayor que overlap")
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks
