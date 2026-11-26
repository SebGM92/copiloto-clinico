import math

from app.embeddings import HashingEmbedder


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))  # los vectores ya vienen normalizados


def test_hashing_embedder_shape_norm_and_determinism():
    e = HashingEmbedder()
    v1, v2 = e.embed(["Metformina en DM2", "Metformina en DM2"])
    assert len(v1) == e.dim == 1024
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0)
    assert v1 == v2


def test_hashing_embedder_shared_words_are_closer():
    q, near, far = HashingEmbedder().embed([
        "dosis de metformina",
        "la dosis de metformina se reduce en enfermedad renal",
        "controlar la presión arterial cada tres meses",
    ])
    assert cos(q, near) > cos(q, far)


def test_hashing_embedder_empty_text_is_zero_vector():
    (v,) = HashingEmbedder().embed([""])
    assert v == [0.0] * 1024
