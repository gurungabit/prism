from __future__ import annotations

from sentence_transformers import SentenceTransformer

from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("embedder")

_model: SentenceTransformer | None = None


class EmbeddingDimensionMismatch(RuntimeError):
    """The configured ``embedding_dimension`` does not match the loaded model.

    ``embedding_dimension`` is wired into the OpenSearch knn_vector mapping
    at index-creation time. A mismatch silently going through would let
    ingest run all the way to the bulk index call, then fail with a
    cryptic shape error after the document has already been parsed,
    chunked, and (in the worst case) had its summary generated. Better
    to fail at model-load before we burn that work.
    """


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("loading_embedding_model", model=settings.embedding_model)
        candidate = SentenceTransformer(settings.embedding_model)
        dimension = candidate.get_sentence_embedding_dimension()
        if dimension is not None and dimension != settings.embedding_dimension:
            # Don't cache the mismatched model -- a later call after the
            # operator fixes the setting should be able to re-load.
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
    """Encode a search query.

    BGE / E5 family models are trained with an asymmetric convention:
    queries get a short instruction prefix ("Represent this sentence
    for searching relevant passages: " for BGE, "query: " for E5),
    passages don't. Skipping the prefix on a BGE-family model leaves
    measurable recall on the table because the query embedding lands
    in a different region of the space than the passage embeddings.

    The prefix is only applied when the configured model name names a
    family known to want it -- otherwise we pass the query through
    untouched (e.g. MiniLM has no such convention).
    """
    model = get_model()
    prefixed = _maybe_prefix_query(query)
    embedding = model.encode(prefixed, normalize_embeddings=True)
    return embedding.tolist()


def _maybe_prefix_query(query: str) -> str:
    name = (settings.embedding_model or "").lower()
    prefix = settings.embedding_query_prefix or ""
    if not prefix:
        return query
    # BGE family. The training prompt ships verbatim with the model
    # card; clients are expected to add it on the query side.
    if "bge" in name:
        return f"{prefix}{query}"
    # E5 family expects ``query: `` on queries and ``passage: `` on
    # passages. The default prefix (designed for BGE) won't match;
    # users who switch to E5 should also override the prefix.
    if name.startswith("intfloat/e5") or "/e5-" in name:
        return f"query: {query}"
    return query
