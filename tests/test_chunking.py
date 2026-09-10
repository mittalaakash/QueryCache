from app.core.chunking import split_into_chunks


def test_split_into_chunks_short_text_is_one_chunk():
    text = "short text"
    assert split_into_chunks(text, size=800, overlap=100) == [text]


def test_split_into_chunks_splits_long_text_with_overlap():
    text = "x" * 2000
    chunks = split_into_chunks(text, size=800, overlap=100)
    assert len(chunks) == 3
    assert all(len(c) <= 800 for c in chunks)
    assert chunks[0][-100:] == chunks[1][:100]
    assert chunks[1][-100:] == chunks[2][:100]


def test_split_into_chunks_empty_text_is_no_chunks():
    assert split_into_chunks("", size=800, overlap=100) == []
