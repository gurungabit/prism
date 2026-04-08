# Deployment

## Local Docker Compose Stack

`docker-compose.yml` provides the infrastructure layer used by local development and `./run.sh`.

```mermaid
graph TB
    subgraph COMPOSE["docker-compose.yml"]
        OS[(OpenSearch<br/>:9200)]
        OSD["OpenSearch Dashboards<br/>:5601"]
        N4J[(Neo4j<br/>:7474 / :7687)]
        PG[(PostgreSQL<br/>:5432)]
        RD[(Redis<br/>:6379)]
        API["API Container<br/>:8000"]
        WEB["UI Container<br/>:3000"]
    end

    OSD --> OS
    API --> OS
    API --> N4J
    API --> PG
    API --> RD
    WEB --> API

    classDef app fill:#2563eb,color:#fff,stroke:none;
    classDef infra fill:#4f46e5,color:#fff,stroke:none;
    classDef aux fill:#64748b,color:#fff,stroke:none;

    class API,WEB app;
    class OS,N4J,PG,RD infra;
    class OSD aux;
```

Important note:

- the compose file exposes the UI container on `:3000`
- the normal local development flow in `./run.sh` runs Vite directly on `:5173`

## Default Local Runtime

When using `./run.sh`, the effective developer-facing ports are:

| Service | Port |
|---|---|
| UI | `5173` |
| API | `8000` |
| OpenSearch | `9200` |
| OpenSearch Dashboards | `5601` |
| Neo4j Browser | `7474` |
| Neo4j Bolt | `7687` |
| PostgreSQL | `5432` |
| Redis | `6379` |
| Ollama | `11434` |

## Service Configuration

| Service | Image / runtime | Notes |
|---|---|---|
| OpenSearch | `opensearchproject/opensearch:2.17.0` | single node, security disabled, kNN enabled |
| OpenSearch Dashboards | `opensearchproject/opensearch-dashboards:2.17.0` | local inspection only |
| Neo4j | `neo4j:5.24-community` | APOC enabled |
| PostgreSQL | `postgres:16-alpine` | document registry + analysis persistence |
| Redis | `redis:7-alpine` | auxiliary local service |
| API | FastAPI / Uvicorn | port `8000` |
| UI | Vite in dev, containerized web app in compose | `5173` in dev, `3000` in compose |

## Volumes

| Volume | Purpose |
|---|---|
| `opensearch-data` | persistent search index data |
| `neo4j-data` | graph persistence |
| `postgres-data` | analysis history, registry, checkpoints |

## Environment Variables

Backend settings use the `PRISM_` prefix.

| Variable | Default | Description |
|---|---|---|
| `PRISM_OPENSEARCH_URL` | `http://localhost:9200` | OpenSearch endpoint |
| `PRISM_NEO4J_URI` | `bolt://localhost:7687` | Neo4j endpoint |
| `PRISM_NEO4J_USER` | `neo4j` | Neo4j username |
| `PRISM_NEO4J_PASSWORD` | `prismgraph` | Neo4j password |
| `PRISM_POSTGRES_URL` | `postgresql://prism:prismpass@localhost:5432/prism` | PostgreSQL DSN |
| `PRISM_REDIS_URL` | `redis://localhost:6379` | Redis endpoint |
| `PRISM_DATA_DIR` | `./data` | data root |
| `PRISM_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | embedding model |
| `PRISM_EMBEDDING_DIMENSION` | `384` | vector dimension |
| `PRISM_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | reranker |
| `PRISM_CHUNK_SIZE_TOKENS` | `500` | target chunk size |
| `PRISM_RETRIEVAL_TOP_K` | `30` | default retrieval window |
| `PRISM_RERANK_TOP_K` | `15` | post-rerank chunk count |
| `PRISM_MAX_RETRIEVAL_ROUNDS` | `2` | max coverage retries |
| `PRISM_STALENESS_THRESHOLD_DAYS` | `365` | stale source threshold |
| `PRISM_MODEL_ROUTER` | `qwen2.5:7b` | routing model |
| `PRISM_MODEL_RISK` | `qwen2.5:7b` | risk model |
| `PRISM_MODEL_SYNTHESIS` | `qwen2.5:7b` | synthesis model |
| `PRISM_MODEL_BULK` | `qwen2.5:7b` | general analysis model |

## Ollama

PRISM expects a local Ollama runtime for LLM-backed features.

```bash
ollama serve
ollama pull qwen2.5:7b
```

If Ollama is unavailable, PRISM still runs but degrades:

- entity extraction falls back to deterministic patterns
- query expansion simplifies
- agent outputs may be partial or empty
- chat cannot produce high-quality grounded answers

## Health Checks

Compose health checks are defined for:

- OpenSearch
- Neo4j
- PostgreSQL
- Redis

`./run.sh` also waits for the API and UI to become reachable before reporting success.

## AWS Migration Path

| Local component | AWS equivalent |
|---|---|
| OpenSearch container | Amazon OpenSearch Service |
| Neo4j container | Neo4j on EC2 or Amazon Neptune |
| PostgreSQL container | Amazon RDS PostgreSQL |
| Redis container | Amazon ElastiCache |
| API process/container | ECS Fargate or EC2 |
| UI static assets | S3 + CloudFront |
| Ollama local runtime | GPU-backed inference service |
