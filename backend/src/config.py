from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_prefix="PRISM_")

    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "prism-chunks"

    postgres_url: str = "postgresql://prism:prismpass@localhost:5432/prism"

    redis_url: str = "redis://localhost:6379"

    data_dir: str = "./data"

    # Filesystem jail for path-based connectors (sharepoint / excel /
    # onenote stubs). ``resolve_local_path`` constrains every
    # ``config.path`` to live inside this subtree -- including symlink
    # destinations -- and rejects requests that escape via ``..`` or a
    # symlink. Defaults to ``./data`` so a fresh deployment is jailed
    # by default; the previous opt-in env var (``PRISM_LOCAL_SOURCE_ROOT``)
    # still works because pydantic-settings maps the field to that name.
    #
    # ``allow_unsandboxed_local_sources`` is the deliberate escape hatch
    # for development workflows that need to walk paths outside the
    # root (e.g. a researcher pointing at a one-off directory). Treat
    # it as "I know what I'm doing"; production deployments leave it
    # off so the security boundary holds.
    local_source_root: str = "./data"
    allow_unsandboxed_local_sources: bool = False

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

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50

    retrieval_top_k: int = 30
    rerank_top_k: int = 15

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
    model_bulk: str = "raptor-mini"


settings = Settings()
