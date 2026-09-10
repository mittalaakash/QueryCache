"""Prometheus metrics for the RAG app, exposed at GET /metrics."""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

QUERY_COUNT = Counter("rag_queries_total", "Total number of RAG queries answered")
QUERY_LATENCY = Histogram("rag_query_latency_seconds", "End-to-end latency of a RAG query")
RETRIEVED_CHUNKS = Histogram(
    "rag_retrieved_chunks", "Number of chunks retrieved per query", buckets=(0, 1, 2, 3, 4, 5, 10)
)
INGESTED_DOCUMENTS = Counter(
    "rag_ingested_documents_total", "Documents processed via the UI ingestion path, by action", ["action"]
)
CACHE_HITS = Counter("rag_cache_hits_total", "Semantic cache hits")
CACHE_MISSES = Counter("rag_cache_misses_total", "Semantic cache misses")


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
