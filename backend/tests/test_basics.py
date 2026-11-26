from app.acronyms import expand
from app.guard import check
from app.ingest.chunker import chunk_text


def test_chunker_overlap():
    chunks = chunk_text("a" * 2500, size=1000, overlap=200)
    assert len(chunks) == 4
    assert all(len(c) <= 1000 for c in chunks)


def test_expand_acronym():
    assert "hipertensión arterial" in expand("tratamiento de HTA")


def test_guard_rejects_empty():
    assert not check("   ").allowed
