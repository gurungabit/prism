# Deployment

## Local Docker Compose Stack

`docker-compose.yml` provides the infrastructure layer used by local development and `./run.sh`.

```mermaid
graph TB
    subgraph COMPOSE["docker-compose.yml"]
        OS[(OpenSearch<br/>:9200)]
        OSD["OpenSearch Dashboards<br/>:5601"]
        PG[(PostgreSQL<br/>:5432)]
        RD[(Redis<br/>:6379)]
        API["API Container<br/>:8000"]
        WEB["UI Container<br/>:3000"]
    end

    OSD --> OS
    API --> OS
    API --> PG
    API --> RD
    WEB --> API

    classDef app fill:#2563eb,color:#fff,stroke:none;
    classDef infra fill:#4f46e5,color:#fff,stroke:none;
    classDef aux fill:#64748b,color:#fff,stroke:none;

    class API,WEB app;
    class OS,PG,RD infra;
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
| PostgreSQL | `5432` |
| Redis | `6379` |
| LLM proxy | `4000` |

## Service Configuration

| Service | Image / runtime | Notes |
|---|---|---|
| OpenSearch | `opensearchproject/opensearch:2.17.0` | single node, security disabled, kNN enabled |
| OpenSearch Dashboards | `opensearchproject/opensearch-dashboards:2.17.0` | local inspection only |
| PostgreSQL | `postgres:16-alpine` | document registry, analysis persistence, relational knowledge store (`kg_*` tables) |
| Redis | `redis:7-alpine` | auxiliary local service |
| API | FastAPI / Uvicorn | port `8000` |
| UI | Vite in dev, containerized web app in compose | `5173` in dev, `3000` in compose |

## Volumes

| Volume | Purpose |
|---|---|
| `opensearch-data` | persistent search index data |
| `postgres-data` | analysis history, registry, knowledge store, checkpoints |

## Environment Variables

Backend settings use the `PRISM_` prefix.

| Variable | Default | Description |
|---|---|---|
| `PRISM_OPENSEARCH_URL` | `http://localhost:9200` | OpenSearch endpoint |
| `PRISM_POSTGRES_URL` | `postgresql://prism:prismpass@localhost:5432/prism` | PostgreSQL DSN |
| `PRISM_REDIS_URL` | `redis://localhost:6379` | Redis endpoint |
| `PRISM_DATA_DIR` | `./data` | data root used by the GitLab connector for caching ingested artifacts. **Not** the jail boundary for path-based connectors -- see `PRISM_LOCAL_SOURCE_ROOT` below. |
| `PRISM_LOCAL_SOURCE_ROOT` | `./data` | filesystem jail for path-based connectors (sharepoint / excel / onenote). Every `config.path` must resolve inside this subtree -- `..` traversal and symlink-escape are rejected. Default-on as of round 11. |
| `PRISM_ALLOW_UNSANDBOXED_LOCAL_SOURCES` | `false` | deliberate escape hatch for development workflows that need a path outside the jail (e.g. a researcher pointing at a one-off directory). Set to `true` to bypass `PRISM_LOCAL_SOURCE_ROOT` entirely. **Production deployments should leave this off.** Missing-path rejection still applies even with the hatch on. |
| `PRISM_GITLAB_BASE_URL` | `https://gitlab.com/api/v4` | GitLab API endpoint; override for self-hosted |
| `PRISM_GITLAB_TOKEN` | `""` | server-wide PAT/service-account token. Used when a source row doesn't carry its own token (the wizard no longer collects per-source tokens). |
| `PRISM_GITLAB_REQUEST_TIMEOUT_SECONDS` | `30.0` | per-request timeout for the GitLab connector |
| `PRISM_GITLAB_MAX_PROJECTS_PER_SOURCE` | `200` | safety cap on group-scoped sources |
| `PRISM_GITLAB_GROUP_ACTIVE_WINDOW_DAYS` | `30` | when ingesting a whole group, skip projects with no activity in the last N days. `0` disables the filter. Single-project ingest is unaffected. |
| `PRISM_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | embedding model |
| `PRISM_EMBEDDING_DIMENSION` | `384` | vector dimension |
| `PRISM_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | reranker |
| `PRISM_CHUNK_SIZE_TOKENS` | `500` | target chunk size |
| `PRISM_RETRIEVAL_TOP_K` | `30` | default retrieval window |
| `PRISM_RERANK_TOP_K` | `15` | post-rerank chunk count |
| `PRISM_MAX_RETRIEVAL_ROUNDS` | `2` | max coverage retries |
| `PRISM_STALENESS_THRESHOLD_DAYS` | `365` | stale source threshold |
| `PRISM_LLM_BASE_URL` | `http://127.0.0.1:4000/v1` | OpenAI-compatible LLM endpoint |
| `PRISM_LLM_API_KEY` | `local-dev` | API key sent to the proxy |
| `PRISM_MODEL_ROUTER` | `gpt-5-mini` | routing model |
| `PRISM_MODEL_RISK` | `gpt-5-mini` | risk model |
| `PRISM_MODEL_SYNTHESIS` | `gpt-5-mini` | synthesis model |
| `PRISM_MODEL_BULK` | `raptor-mini` | general analysis model |

## LLM Proxy

PRISM talks to any OpenAI-compatible endpoint via `PRISM_LLM_BASE_URL`. The default is a local proxy listening on `http://127.0.0.1:4000/v1` that handles upstream auth and serves aliases such as `gpt-5-mini`, `raptor-mini`, `claude-opus-4.6-fast`, `gemini-2.5-pro`, and `minimax-2.5`.

Start the proxy before running PRISM. Any OpenAI-compatible server works — swap the base URL, API key, and model aliases via the `PRISM_*` env vars above.

If the proxy is unreachable, PRISM still runs but degrades:

- query expansion simplifies
- agent outputs may be partial or empty
- chat cannot produce high-quality grounded answers
- LLM-generated turn titles never land (UI falls back to the raw
  requirement text as the turn header)

## Health Checks

Compose health checks are defined for:

- OpenSearch
- PostgreSQL
- Redis

`./run.sh` also waits for the API and UI to become reachable before reporting success.

### Wipe and restart

`./run.sh --clean` runs `docker compose down -v` before bringing services
up, which wipes the Postgres + OpenSearch + Redis volumes. Useful when
iterating on schema changes that aren't bridged by `ALTER TABLE`
self-healing migrations -- the bootstrap path runs every `CREATE TABLE
IF NOT EXISTS` again on first connection.

### Orphaned sources on restart

When the API process is killed mid-ingest, the `sources` row stays at
`status='syncing'` until something moves it. On startup, the lifespan hook
in `main.py` flips every `syncing` row to `error` with
`last_error='Ingest interrupted by restart'`, so the UI's Sync button
unlocks without a manual SQL nudge.

## AWS Migration Path

| Local component | AWS equivalent |
|---|---|
| OpenSearch container | Amazon OpenSearch Service |
| PostgreSQL container | Amazon RDS PostgreSQL |
| Redis container | Amazon ElastiCache |
| API process/container | ECS Fargate or EC2 |
| UI static assets | S3 + CloudFront |
| Local LLM proxy | Managed OpenAI-compatible endpoint (Bedrock, Azure OpenAI, vLLM, etc.) |
