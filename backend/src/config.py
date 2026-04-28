from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ``env_file`` is resolved relative to the process CWD. Both
    # ``run.sh`` and the .claude/launch.json ``backend-api`` config set
    # CWD to ``backend/``, so ``.env`` lands at ``backend/.env`` -- which
    # is what ``.gitignore`` is already covering. ``extra="ignore"``
    # keeps the loader from raising when the .env carries non-PRISM
    # keys (e.g. a developer pasted unrelated env vars).
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

    # Filesystem jail for path-based connectors (sharepoint / excel /
    # onenote stubs). ``resolve_local_path`` constrains every
    # ``config.path`` to live inside this subtree -- including symlink
    # destinations -- and rejects requests that escape via ``..`` or a
    # symlink. Defaults to ``./data`` so a fresh deployment is jailed
    # by default.
    #
    # ``allow_unsandboxed_local_sources`` is the deliberate escape hatch
    # for development workflows that need to walk paths outside the
    # root (e.g. a researcher pointing at a one-off directory). Treat
    # it as "I know what I'm doing"; production deployments leave it
    # off so the security boundary holds.
    local_source_root: str = "./data"
    allow_unsandboxed_local_sources: bool = False

    # Comma-separated browser origins allowed to call the API.
    # ``*`` is a local-experiment escape hatch; credentials are disabled
    # for that sentinel in main.py.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse ``cors_origins`` into a list of stripped non-empty strings."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # GitLab connector defaults. Overridable per-source via ``config.base_url``.
    # Self-hosted instances set PRISM_GITLAB_BASE_URL at deploy time.
    gitlab_base_url: str = "https://gitlab.com/api/v4"
    # Server-wide PAT / service-account token. Used when a source doesn't
    # carry its own token (see ``GitLabConnector`` fallback). Set via
    # ``PRISM_GITLAB_TOKEN`` at deploy time. Kept as a string rather than
    # Secret so it can be passed through httpx headers directly.
    gitlab_token: str = ""
    gitlab_request_timeout_seconds: float = 30.0
    # Cap on number of projects walked when ingesting a whole-group source.
    # Per-project doc count is uncapped -- pull every knowledge file in the
    # repo regardless of size.
    gitlab_max_projects_per_source: int = 200
    # When ingesting a whole group, skip projects with no activity in the
    # last N days. Mirrors GitLab's "active" filter -- avoids spending
    # ingest budget on dormant / archived-but-not-flagged repos. Set to 0
    # to disable the filter and walk every project.
    gitlab_group_active_window_days: int = 30

    # Embedding model. ``BAAI/bge-base-en-v1.5`` (768 dim) is the default
    # because it materially outperforms MiniLM on terminology-mismatch
    # retrieval (e.g. README says "Integrations", user asks about
    # "calls"). Switching models means re-indexing -- the OpenSearch
    # mapping uses ``embedding_dimension`` at index-creation time, so an
    # existing index with a different dimension will reject inserts.
    # Wipe with ``./run.sh --clean`` and re-ingest after changing.
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimension: int = 768
    # BGE / E5 family models are trained with an asymmetric query/passage
    # convention: queries get a short instruction prefix, passages don't.
    # ``embed_query`` honors this when the model name matches; passages
    # are embedded raw. Override only if you swap to a model that wants
    # a different prefix (e.g. ``query: `` for E5).
    embedding_query_prefix: str = (
        "Represent this sentence for searching relevant passages: "
    )

    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    # Floor below which a vector-search hit is dropped. Set to 0.0 to
    # disable -- the RRF merge already discounts low-rank vector hits,
    # and a hard floor calibrated for one model (the old MiniLM cutoff
    # was 0.6) silently nukes legitimate matches under a different
    # embedding family. Disabled by default; tune per-deploy if needed.
    vector_min_score: float = 0.0

    retrieval_top_k: int = 30
    rerank_top_k: int = 15

    # Chat-surface retrieval knobs. Distinct from the analyze-surface
    # ``retrieval_top_k`` because chat used to hard-code ``top_k=10`` /
    # ``expand=False`` in the route -- which made chat noticeably worse
    # than analyze on the same query. The defaults here mirror analyze's
    # better recall, then the reranker trims back down to a tight prompt
    # context.
    chat_retrieval_top_k: int = 30
    chat_query_expansion: bool = True
    chat_rerank: bool = True
    chat_rerank_top_k: int = 8
    chat_prompt_chunks: int = 6
    chat_chunk_chars: int = 2500
    chat_use_hyde: bool = True
    # Agentic refinement: if the first pass returns thin / low-confidence
    # results, reformulate the query and search once more. Bounded to a
    # single retry per turn so a degenerate query can't spiral.
    chat_agentic_refine: bool = True
    chat_refine_max_score: float = 0.05
    chat_refine_min_chunks: int = 3

    # HyDE settings (used when ``use_hyde=True`` is passed to search()).
    hyde_max_chars: int = 600

    # Per-document summary chunks. When enabled, ingestion emits one
    # extra synthetic chunk per document containing an LLM-generated
    # abstract over the whole doc. These compete with section chunks at
    # retrieval time and dramatically improve recall for "what does
    # X do / call / depend on" style queries.
    enable_document_summaries: bool = True
    document_summary_max_input_chars: int = 12000

    max_retrieval_rounds: int = 2

    agent_timeout_seconds: int = 30
    global_timeout_seconds: int = 300

    temporal_decay_scale_days: int = 180
    staleness_threshold_days: int = 365

    dedup_threshold: float = 0.8
    dedup_num_perm: int = 128

    llm_base_url: str = "http://127.0.0.1:4000/v1"
    llm_api_key: str = "local-dev"

    model_router: str = "gpt-5-mini"
    model_risk: str = "gpt-5-mini"
    model_synthesis: str = "gpt-5-mini"
    # ``model_bulk`` is the high-volume / low-stakes model: per-doc
    # summaries at ingest time, query expansion variants, HyDE
    # hypotheticals, agentic refine rewrites. Was ``raptor-mini`` --
    # which is fine when the LiteLLM proxy carries that alias, but on
    # proxies that only know the standard OpenAI lineup the bulk
    # endpoints all 401'd while chat / analysis (using ``gpt-5-mini``)
    # kept working. Default everyone to ``gpt-5-mini`` so a fresh
    # proxy ``just works``; override per-deployment via
    # ``PRISM_MODEL_BULK`` when a cheaper bulk alias is available.
    model_bulk: str = "gpt-5-mini"


settings = Settings()
