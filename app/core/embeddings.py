"""Single shared Ollama embedding model instance, so ingestion and query-time
retrieval always embed with the exact same model/config."""

from langchain_ollama import OllamaEmbeddings

from app.config import settings

embedder = OllamaEmbeddings(model=settings.ollama_embed_model)
