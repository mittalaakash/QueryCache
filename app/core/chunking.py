"""Character-based text chunking for embedding. A fixed-size sliding window
with overlap is enough at this corpus size/shape — no need for a heavier
splitter library."""


def split_into_chunks(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks = []
    step = size - overlap
    start = 0
    while start < len(text):
        chunk = text[start:start + size]
        chunks.append(chunk)
        if start + size >= len(text):
            break
        start += step
    return chunks
