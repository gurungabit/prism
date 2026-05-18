from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PRISM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "prism-chunks"

    postgres_url: str = "postgresql://prism:prismpass@localhost:5432/prism"

    redis_url: str = "redis://localhost:6379"

    # Filesystem jail for path-based connectors. ``resolve_local_path``
    # constrains every ``config.path`` to live inside this subtree --
    # including symlink destinations -- and rejects paths that escape
    # via ``..`` or a symlink. ``allow_unsandboxed_local_sources`` is
    # the deliberate escape hatch; production leaves it off.
    local_source_root: str = "./data"
    allow_unsandboxed_local_sources: bool = False

    # ``*`` is a local-experiment escape hatch; credentials are disabled
    # for that sentinel in main.py.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse ``cors_origins`` into a list of stripped non-empty strings."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    gitlab_base_url: str = "https://gitlab.com/api/v4"
    gitlab_token: str = ""
    gitlab_request_timeout_seconds: float = 30.0
    gitlab_max_projects_per_source: int = 200
    # Skip projects with no activity in the last N days. ``0`` disables.
    gitlab_group_active_window_days: int = 30

    # Switching embedding model requires re-indexing: the OpenSearch
    # knn_vector mapping bakes in ``embedding_dimension`` at
    # index-creation time. ``./run.sh --clean`` to wipe and re-ingest.
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimension: int = 768
    # BGE / E5 are trained with asymmetric query/passage encoding;
    # ``embed_query`` prepends this on queries only.
    embedding_query_prefix: str = (
        "Represent this sentence for searching relevant passages: "
    )

    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    chunking_strategy: Literal["semantic", "structural"] = "semantic"
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    semantic_chunk_min_tokens: int = 120
    semantic_chunk_breakpoint_percentile: float = 80.0
    semantic_chunk_breakpoint_threshold: float = 0.2
    # Vector-hit floor before RRF merge. ``0.0`` disables. A non-zero
    # cutoff is calibrated per embedding family -- if you change models,
    # retune or leave this at zero.
    vector_min_score: float = 0.0

    retrieval_top_k: int = 30
    rerank_top_k: int = 15
    analysis_use_hyde: bool = True
    analysis_agentic_refine: bool = True
    analysis_refine_max_score: float = 0.05
    analysis_refine_min_chunks: int = 3

    chat_retrieval_top_k: int = 30
    chat_query_expansion: bool = True
    chat_rerank: bool = True
    chat_rerank_top_k: int = 8
    chat_prompt_chunks: int = 6
    chat_chunk_chars: int = 2500
    chat_use_hyde: bool = True
    chat_agentic_refine: bool = True
    chat_refine_max_score: float = 0.05
    chat_refine_min_chunks: int = 3

    hyde_max_chars: int = 600

    enable_document_summaries: bool = True
    document_summary_max_input_chars: int = 12000
    document_summary_concurrency: int = 8

    max_retrieval_rounds: int = 2

    agent_timeout_seconds: int = 30
    global_timeout_seconds: int = 300

    temporal_decay_scale_days: int = 180
    staleness_threshold_days: int = 365

    dedup_threshold: float = 0.8
    dedup_num_perm: int = 128

    llm_base_url: str = "http://127.0.0.1:4100/v1"
    llm_api_key: str = "local-dev"

    model_router: str = "gpt-5.3-codex-spark"
    model_risk: str = "gpt-5.3-codex-spark"
    model_synthesis: str = "gpt-5.3-codex-spark"
    model_bulk: str = "gpt-5.3-codex-spark"


settings = Settings()
