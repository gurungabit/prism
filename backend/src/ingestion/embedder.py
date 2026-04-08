from __future__ import annotations

from sentence_transformers import SentenceTransformer

from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("embedder")

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("loading_embedding_model", model=settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
        log.info("embedding_model_loaded", dimension=_model.get_sentence_embedding_dimension())
    return _model


def embed_chunks(chunks: list[Chunk], batch_size: int = 64) -> list[Chunk]:
    if not chunks:
        return chunks

    model = get_model()
    texts = [c.content for c in chunks]

    log.info("embedding_chunks", count=len(texts), batch_size=batch_size)
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding.tolist()

    log.info("embedding_complete", count=len(chunks))
    return chunks


def embed_query(query: str) -> list[float]:
    model = get_model()
    embedding = model.encode(query, normalize_embeddings=True)
    return embedding.tolist()
