from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_prefix="PRISM_")

    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "prism-chunks"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "prismgraph"

    postgres_url: str = "postgresql://prism:prismpass@localhost:5432/prism"

    redis_url: str = "redis://localhost:6379"

    data_dir: str = "./data"

    gitlab_token: str = ""
    gitlab_base_url: str = "https://gitlab.com"
    gitlab_group_ids: str = ""  # comma-separated group IDs or full-paths

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

    ollama_host: str = "http://localhost:11434"

    model_router: str = "qwen2.5:7b"
    model_risk: str = "qwen2.5:7b"
    model_synthesis: str = "qwen2.5:7b"
    model_bulk: str = "qwen2.5:7b"


settings = Settings()
