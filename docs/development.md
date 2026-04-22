# Development

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | via `uv` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| bun | 1.3+ | `curl -fsSL https://bun.sh/install \| bash` |
| Docker | 24+ | [docker.com](https://docker.com) |
| LLM proxy | running on `127.0.0.1:4000` | OpenAI-compatible endpoint |

## Local Setup

### Backend

```bash
cd backend
uv sync
uv run uvicorn src.main:app --reload --port 8000
```

### Frontend

```bash
cd ui
bun install
bun dev --port 5173
```

### Infrastructure

```bash
docker compose up -d opensearch postgres redis
```

### First Run

```bash
cd backend
uv run python ../scripts/setup_opensearch.py
# Then open http://localhost:5173/setup to declare org → team → service → source
# and trigger ingestion from the UI. Or drive it from the CLI once you have a
# source declared:
uv run python ../scripts/ingest.py --list                     # list declared sources
uv run python ../scripts/ingest.py --source-id <uuid>         # ingest one
uv run python ../scripts/ingest.py --source-id <uuid> --force # force re-index
```

Or run the project root helper, which starts everything and drops you at the
setup wizard on first boot:

```bash
./run.sh
```

## Testing

### Backend

```bash
cd backend
uv run --with pytest pytest -q tests
```

Current backend suite covers:

- API routes
- chunking
- connectors
- deduplication
- entity extraction
- hybrid search
- orchestrator behavior
- parsing
- report models

### Frontend Build Check

```bash
cd ui
./node_modules/.bin/tsc -b
./node_modules/.bin/vite build
```

## Project Structure

### Backend

```text
backend/src/
├── main.py                    FastAPI entry point + lifespan cleanup
├── config.py                  Settings
├── db.py                      Shared PostgreSQL pool helpers
├── llm_client.py              Shared OpenAI-compatible LLM client
│
├── connectors/
│   ├── base.py
│   ├── gitlab.py
│   ├── sharepoint.py
│   ├── excel.py
│   └── onenote.py
│
├── ingestion/
│   ├── pipeline.py
│   ├── parser.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── deduplicator.py
│   ├── indexer.py
│   ├── registry.py
│   ├── analysis_store.py
│   ├── knowledge_store.py
│   ├── entity_extractor.py
│   └── team_names.py
│
├── retrieval/
│   ├── hybrid_search.py
│   ├── query_expansion.py
│   ├── reranker.py
│   └── knowledge_queries.py
│
├── agents/
│   ├── orchestrator.py
│   ├── llm.py
│   ├── prompts.py
│   ├── schemas.py
│   ├── result.py
│   ├── state_codec.py
│   ├── step_callbacks.py
│   ├── retrieval_agent.py
│   ├── router_agent.py
│   ├── dependency_agent.py
│   ├── risk_effort_agent.py
│   ├── coverage_agent.py
│   └── citation_agent.py
│
├── api/
│   ├── routes.py
│   ├── chat.py
│   └── streaming.py
│
├── models/
│   ├── chunk.py
│   ├── document.py
│   └── report.py
│
└── observability/
    └── logging.py
```

### Frontend

```text
ui/src/
├── App.tsx
├── main.tsx
├── router.tsx
├── index.css
│
├── routes/
│   ├── index.tsx
│   ├── analyze.tsx
│   ├── analyze.$runId.tsx
│   ├── search.tsx
│   ├── chat.tsx
│   ├── chat.$conversationId.tsx
│   ├── history.tsx
│   └── sources.tsx
│
├── components/
│   ├── analysis/
│   ├── chat/
│   ├── layout/
│   ├── search/
│   ├── shared/
│   └── sources/
│
├── hooks/
├── stores/
└── lib/
    ├── api.ts
    ├── schemas.ts
    ├── stream.ts
    └── reportPdf.ts
```

## Extension Points

### Add A Connector

1. Create `backend/src/connectors/<platform>.py`
2. Implement the connector interface
3. Register it in the connector registry
4. Add any new source shape handling needed by ingestion
5. Add representative fixtures or tests

### Add An Agent

1. Create `backend/src/agents/<agent>.py`
2. Define its output schema in `backend/src/agents/schemas.py`
3. Add prompt builders in `backend/src/agents/prompts.py`
4. Register the node in `backend/src/agents/orchestrator.py`
5. Update report synthesis if the new agent contributes to the final report
6. Add regression coverage

### Update The Report Export

PDF export lives in:

- `ui/src/lib/reportPdf.ts`

If the report model changes, update both:

- the API/response schemas in `ui/src/lib/schemas.ts`
- the PDF renderer in `ui/src/lib/reportPdf.ts`

## Practical Tuning Knobs

| Area | Where | Effect |
|---|---|---|
| Chunk size | `config.py` | Larger chunks increase context and reduce granularity |
| Retrieval top-k | `config.py` | Higher values improve recall and cost more |
| Rerank top-k | `config.py` | Controls how many chunks each agent sees |
| Retrieval rounds | `config.py` | More rounds improve coverage, slow analysis |
| Staleness threshold | `config.py` | Controls stale-source warnings |
| Search page size | `backend/src/api/routes.py` | Changes search pagination size |
