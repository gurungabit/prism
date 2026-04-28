from __future__ import annotations

from sentence_transformers import SentenceTransformer

from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("embedder")

_model: SentenceTransformer | None = None


class EmbeddingDimensionMismatch(RuntimeError):
    """Configured ``embedding_dimension`` doesn't match the loaded model."""


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("loading_embedding_model", model=settings.embedding_model)
        candidate = SentenceTransformer(settings.embedding_model)
        dimension = candidate.get_sentence_embedding_dimension()
        if dimension is not None and dimension != settings.embedding_dimension:
            # Don't cache the mismatched model so a re-load can succeed
            # after the operator fixes the setting.
            raise EmbeddingDimensionMismatch(
                f"Embedding model '{settings.embedding_model}' has dimension "
                f"{dimension}, but PRISM_EMBEDDING_DIMENSION is configured "
                f"as {settings.embedding_dimension}. Set "
                f"PRISM_EMBEDDING_DIMENSION={dimension} to match the model "
                f"and wipe the OpenSearch index (./run.sh --clean) before "
                f"re-ingesting."
            )
        log.info("embedding_model_loaded", dimension=dimension)
        _model = candidate
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
    """Encode a search query, applying any model-specific prefix."""
    model = get_model()
    prefixed = _maybe_prefix_query(query)
    embedding = model.encode(prefixed, normalize_embeddings=True)
    return embedding.tolist()


def _maybe_prefix_query(query: str) -> str:
    # BGE / E5 are trained with asymmetric query/passage encoding:
    # queries get a short instruction, passages don't. Skipping the
    # prefix on a BGE-family model leaves recall on the table.
    name = (settings.embedding_model or "").lower()
    prefix = settings.embedding_query_prefix or ""
    if not prefix:
        return query
    if "bge" in name:
        return f"{prefix}{query}"
    if name.startswith("intfloat/e5") or "/e5-" in name:
        return f"query: {query}"
    return query
