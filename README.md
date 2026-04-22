# PRISM

**Platform-aware Requirement Intelligence and Service Mapping**

PRISM turns a product or platform requirement into a cross-team analysis
brief grounded in your internal documentation. It uses a **declared**
Org → Team → Service hierarchy so every retrieved document has known
provenance — no regex-inferred ownership, no guessing from folder paths.

```mermaid
graph TB
    subgraph UX["User Experience"]
        SETUP["Setup<br/>Declare org · teams · services"]
        SEARCH["Search<br/>Scope-aware hybrid retrieval"]
        CHAT["Chat<br/>Grounded answers"]
        ANALYZE["Analyze<br/>Multi-agent brief"]
        SOURCES["Sources<br/>Attach · sync · inspect"]
        EXPORT["Export<br/>PDF brief"]
    end

    subgraph APP["Application Layer"]
        API["FastAPI API<br/>REST + SSE"]
        CATAPI["Catalog API<br/>orgs · teams · services · sources"]
        ORC["LangGraph Orchestrator<br/>Analysis workflow"]
        RET["Hybrid Retrieval<br/>BM25 + vector + scope filter"]
    end

    subgraph DATA["Knowledge Stores"]
        OS[(OpenSearch)]
        PG[(PostgreSQL<br/>Catalog · Registry · History)]
    end

    subgraph AI["AI Runtime"]
        OLLAMA["LLM Proxy<br/>OpenAI-compatible"]
    end

    SETUP --> CATAPI
    SOURCES --> CATAPI
    SEARCH --> API
    CHAT --> API
    ANALYZE --> API
    API --> RET
    API --> ORC
    CATAPI --> PG
    ORC --> OLLAMA
    RET --> OS
    ORC --> PG
    ANALYZE --> EXPORT

    classDef ux fill:#0f766e,color:#fff,stroke:none;
    classDef app fill:#2563eb,color:#fff,stroke:none;
    classDef agent fill:#f59e0b,color:#fff,stroke:none;
    classDef data fill:#6366f1,color:#fff,stroke:none;
    classDef ai fill:#e11d48,color:#fff,stroke:none;

    class SETUP,SEARCH,CHAT,ANALYZE,SOURCES,EXPORT ux;
    class API,CATAPI,RET app;
    class ORC agent;
    class OS,PG data;
    class OLLAMA ai;
```

## What PRISM Does

- Declares an explicit `Organization → Team → Service` hierarchy so document
  provenance is never inferred
- Attaches **sources** (GitLab projects or groups, etc.) at any of those
  three scopes — documents ingested by a source inherit its scope
- Analyzes a structured requirement brief (not just a one-liner)
- Recommends a primary owning team and supporting teams
- Identifies services in scope and related dependencies
- Surfaces risks, effort, blockers, evidence quality, and unsupported claims
- Streams live agent progress while the analysis is running
- Supports scope-aware search: filter by org/team/service without losing the
  hybrid BM25 + vector retrieval pipeline
- Supports grounded chat with source citations and chunk previews
- Exports completed analyses as readable PDFs

## Product Surfaces

| Surface | What it does |
|---|---|
| **Setup** | First-run wizard to declare the org, teams, services |
| Dashboard | Health, recent analyses, declared teams, quick entry points |
| Analyze | Structured requirement intake and live multi-agent analysis |
| Search | Hybrid retrieval over the knowledge base with scope + filters |
| Chat | Retrieval-grounded Q&A with source references and citation previews |
| **Sources** | Declared-source inventory; per-source status, sync, docs |
| **Sources → new** | 4-step wizard: scope → connector → config → test + save |
| Org / Team / Service pages | Declared catalog pages; attach sources at any scope |
| History | Past analysis runs with status and deletion |

## Quickstart

```bash
./run.sh
```

This single command:

1. Installs backend dependencies with `uv`
2. Installs frontend dependencies with `bun`
3. Starts infrastructure with Docker Compose (OpenSearch, PostgreSQL, Redis)
4. Configures OpenSearch
5. Starts the API on `http://localhost:8000`
6. Starts the UI on `http://localhost:5173`

On first boot, open [http://localhost:5173/setup](http://localhost:5173/setup)
and declare your org, a team, and (optionally) your first service. Then
attach a GitLab source to ingest real docs.

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [bun](https://bun.sh/)
- [Docker](https://www.docker.com/)
- An OpenAI-compatible LLM endpoint on `http://127.0.0.1:4000/v1`
  (override with `PRISM_LLM_BASE_URL`)
- A GitLab personal access token with `read_api` + `read_repository` scopes
  for Phase 1 ingestion. Self-hosted GitLab? Set `PRISM_GITLAB_BASE_URL`.

## Declarative Ownership Model

```
Organization
 ├── Sources (scope = org)              ← visible to every team in the org
 └── Teams
      ├── Sources (scope = team)        ← visible only to this team's analyses
      └── Services
           └── Sources (scope = service) ← narrowest; the service's own docs/repo
```

Every ingested document carries denormalized `(org_id, team_id, service_id)`
columns. Retrieval pushes a scope filter straight into OpenSearch:

```sql
WHERE org_id = Z
  AND (team_id    IS NULL OR team_id    = X)
  AND (service_id IS NULL OR service_id = Y)
```

Org chunks always match. Team chunks match only when their team is in
scope. Service chunks match only their own service.

## Analysis Input

PRISM accepts a structured analysis brief:

```json
{
  "requirement": "Add MFA to customer portal",
  "business_goal": "Reduce account takeover risk before enterprise rollout",
  "context": "Portal already supports email/password login and audit logging",
  "constraints": "Do not break existing mobile login flow",
  "known_teams": "Platform Team, Security Team",
  "known_services": "auth-service, customer-portal",
  "questions_to_answer": "Who should own this work? What dependencies could block it?"
}
```

## Architecture

PRISM has two main runtime paths:

- **Analysis**: FastAPI → LangGraph orchestrator → retrieval (with scope
  filter) + specialist agents → persisted report
- **Search / chat**: FastAPI → hybrid retrieval → scope-filtered results
  or grounded chat answer

```mermaid
graph TB
    subgraph FE["Frontend"]
        UI["React UI<br/>TanStack Router · Zustand · Tailwind"]
    end

    subgraph API["API Layer"]
        FASTAPI["FastAPI Server<br/>REST · SSE"]
        CATALOG["Catalog routes<br/>/api/orgs · teams · services · sources"]
    end

    subgraph ANALYSIS["Analysis Engine"]
        ORC["LangGraph Orchestrator"]
        PIPE["Retrieval → Router → Dependencies<br/>→ Risk/Effort → Coverage → Citations → Synthesis"]
    end

    subgraph INFRA["Infrastructure"]
        PG[(PostgreSQL 16<br/>Orgs · Teams · Services · Sources<br/>Documents · Dependencies · Registry · History)]
        OS[(OpenSearch 2.17<br/>Chunks · Embeddings<br/>+ scope fields)]
    end

    subgraph AI["AI"]
        OLLAMA["LLM Proxy<br/>OpenAI-compatible"]
    end

    UI -->|Setup · Analyze · Search · Chat · Sources · History| FASTAPI
    UI --> CATALOG
    FASTAPI --> ORC
    ORC --> PIPE
    FASTAPI --> OS
    FASTAPI --> PG
    CATALOG --> PG
    PIPE --> OS
    PIPE --> PG
    PIPE --> OLLAMA
    FASTAPI --> OLLAMA

    classDef frontend fill:#3b82f6,color:#fff,stroke:none;
    classDef api fill:#10b981,color:#fff,stroke:none;
    classDef worker fill:#f59e0b,color:#fff,stroke:none;
    classDef infra fill:#6366f1,color:#fff,stroke:none;
    classDef ai fill:#f43f5e,color:#fff,stroke:none;

    class UI frontend;
    class FASTAPI,CATALOG api;
    class ORC,PIPE worker;
    class PG,OS infra;
    class OLLAMA ai;
```

See [docs/architecture.md](docs/architecture.md) for detailed diagrams and
runtime notes.

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Topology, declared catalog, runtime flows, data stores |
| [Data Flow](docs/data-flow.md) | Declared sources, ingestion, retrieval, scope filtering |
| [Agents](docs/agents.md) | Agent responsibilities, orchestration, state, degradation |
| [API Reference](docs/api.md) | Analysis, search, catalog, sources, chat endpoints |
| [Deployment](docs/deployment.md) | Docker Compose setup, ports, env vars |
| [Development](docs/development.md) | Local setup, tests, project structure, extension points |
| [plan.md](plan.md) | Design rationale for the declarative ownership model |

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Configurable via OpenAI-compatible proxy (default `gpt-5-mini`) |
| Search | OpenSearch 2.17 hybrid retrieval with scope field pushdown |
| Knowledge Store | PostgreSQL relational tables (declared catalog + `kg_*` + registry) |
| Persistence | PostgreSQL 16 |
| Agent Framework | LangGraph with PostgreSQL checkpointing |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Re-ranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Backend | FastAPI + Python 3.12 (asyncpg, httpx) |
| Frontend | React 18.3 + TypeScript + Tailwind CSS + TanStack Router |
| Export | jsPDF + jspdf-autotable |

## Project Structure

```text
prism/
├── run.sh
├── docker-compose.yml
├── plan.md                       # design rationale for declarative ownership
├── backend/
│   ├── src/
│   │   ├── agents/
│   │   ├── api/
│   │   │   ├── routes.py         # analysis, search, chat, graph
│   │   │   └── catalog_routes.py # orgs / teams / services / sources CRUD
│   │   ├── catalog/              # declared-catalog schema + repos
│   │   ├── connectors/           # gitlab (API) + sharepoint/excel/onenote (local)
│   │   ├── ingestion/
│   │   ├── models/
│   │   ├── retrieval/
│   │   ├── db.py
│   │   └── llm_client.py
│   └── tests/
├── ui/
│   └── src/
│       ├── components/
│       ├── hooks/
│       │   └── useCatalog.ts     # org / team / service / source hooks
│       ├── lib/api.ts            # typed API client
│       ├── routes/
│       │   ├── setup.tsx         # first-run wizard
│       │   ├── orgs.$orgId.tsx
│       │   ├── teams.$teamId.tsx
│       │   ├── services.$serviceId.tsx
│       │   ├── sources.tsx
│       │   ├── sources.new.tsx   # 4-step source wizard
│       │   └── sources.$sourceId.tsx
│       └── stores/
├── scripts/
│   ├── ingest.py                 # CLI: ingest a declared source
│   └── setup_opensearch.py
├── data/                         # empty by default; path-based connectors opt-in
└── docs/
```

## Verification

Current local verification targets:

- Backend test suite: **50 tests** (5 additional Postgres-gated tests skipped
  without `PRISM_POSTGRES_URL`)
- Frontend build: `tsc -b && vite build`

Run the backend suite:

```bash
cd backend && uv run pytest
```

Run the catalog / API tests against a local PostgreSQL:

```bash
PRISM_POSTGRES_URL=postgresql://prism:prismpass@localhost:5432/prism \
  uv run pytest
```

## License

Internal POC. Not licensed for distribution.
