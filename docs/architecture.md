# Architecture

## System Topology

PRISM has two primary product paths:

- **Analysis** for long-running, multi-agent requirement briefs
- **Search and chat** for direct retrieval over the same knowledge base

Both run on top of the **declared catalog** (organizations → teams → services)
and the **declared sources** attached to those entities. Ingested documents
carry a scope pointer `(org_id, team_id, service_id)` directly — no inference.

```mermaid
graph TB
    subgraph CLIENT["Client Surfaces"]
        DASH["Dashboard"]
        ANALYZE["Analyze"]
        SEARCH["Search"]
        CHAT["Chat"]
        SETUP["Setup wizard"]
        SOURCES["Sources + detail"]
        HISTORY["History"]
    end

    subgraph API_LAYER["Application Layer"]
        API["FastAPI API<br/>Port 8000"]
        CATAPI["Catalog Routes<br/>/api/orgs · /api/teams · /api/services · /api/sources"]
        STREAM["SSE Streaming<br/>Analysis + chat"]
    end

    subgraph ENGINE["Analysis Engine"]
        ORC["LangGraph Orchestrator"]
        RET["Retrieval"]
        RTR["Router"]
        DEP["Dependencies"]
        RSK["Risk + Effort"]
        COV["Coverage"]
        CIT["Citations"]
        SYN["Synthesis"]
    end

    subgraph RETRIEVAL["Retrieval + Intelligence"]
        HS["Hybrid Search<br/>BM25 + vector + scope filter"]
        RRK["Cross-encoder<br/>Reranker"]
        LLM["LLM Proxy<br/>OpenAI-compatible"]
    end

    subgraph DATA["Data Stores"]
        OS[(OpenSearch)]
        CAT[(Declared Catalog<br/>orgs · teams · services · sources)]
        PG[(PostgreSQL)]
    end

    DASH --> API
    ANALYZE --> API
    SEARCH --> API
    CHAT --> API
    SETUP --> CATAPI
    SOURCES --> CATAPI
    HISTORY --> API
    API --> STREAM
    CATAPI --> CAT

    API --> ORC
    ORC --> RET --> RTR --> DEP --> RSK --> COV --> CIT --> SYN
    RET --> HS --> RRK
    HS --> OS
    RTR --> CAT
    DEP --> CAT
    RTR --> LLM
    DEP --> LLM
    RSK --> LLM
    COV --> LLM
    CIT --> LLM
    SYN --> LLM
    API --> HS
    API --> PG
    ORC -. checkpoints + persisted reports .-> PG

    classDef client fill:#0f766e,color:#fff,stroke:none;
    classDef api fill:#2563eb,color:#fff,stroke:none;
    classDef engine fill:#f59e0b,color:#fff,stroke:none;
    classDef retrieval fill:#7c3aed,color:#fff,stroke:none;
    classDef data fill:#4f46e5,color:#fff,stroke:none;
    classDef ai fill:#e11d48,color:#fff,stroke:none;

    class DASH,ANALYZE,SEARCH,CHAT,SETUP,SOURCES,HISTORY client;
    class API,CATAPI,STREAM api;
    class ORC,RET,RTR,DEP,RSK,COV,CIT,SYN engine;
    class HS,RRK retrieval;
    class OS,CAT,PG data;
    class LLM ai;
```

## The Declarative Ownership Model

PRISM replaces regex-inferred ownership with an explicit hierarchy. See
[plan.md](../plan.md) for the design rationale.

```
Organization
 ├── Sources (scope = org)              ← visible to every team in the org
 └── Teams
      ├── Sources (scope = team)        ← visible only to this team's analyses
      └── Services
           └── Sources (scope = service) ← narrowest; the service's own docs
```

Every ingested document inherits the `(org_id, team_id, service_id)` triple
from its source. A chunk's scope is non-negotiable: it is what was declared
at ingest time, not what the text might have implied.

### Retrieval filter semantics

For an analysis routed to **Team X, Service Y, Org Z**, the filter is:

```sql
WHERE org_id = Z
  AND (team_id    IS NULL OR team_id    = X)
  AND (service_id IS NULL OR service_id = Y)
```

Org-scoped chunks always match. Team chunks match only when their team is
in scope. Service chunks match only their own service. The filter pushes
down to OpenSearch as `bool` clauses — no scoring impact, huge precision
win.

## Catalog Schema

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ TEAMS : has
    ORGANIZATIONS ||--o{ SOURCES : "scope=org"
    TEAMS ||--o{ SERVICES : has
    TEAMS ||--o{ SOURCES : "scope=team"
    SERVICES ||--o{ SOURCES : "scope=service"
    SOURCES ||--o{ KG_DOCUMENTS : ingests
    SOURCES ||--o{ DOCUMENT_REGISTRY : tracks
    SOURCES ||--|| SOURCE_SECRETS : has
    SERVICES ||--o{ KG_DEPENDENCIES : from
    SERVICES ||--o{ KG_DEPENDENCIES : to
    SERVICES ||--o{ KG_PENDING_DEPENDENCIES : from

    ORGANIZATIONS {
        uuid id PK
        text name UK
    }
    TEAMS {
        uuid id PK
        uuid org_id FK
        text name
    }
    SERVICES {
        uuid id PK
        uuid team_id FK
        text name
        text repo_url
    }
    SOURCES {
        uuid id PK
        uuid org_id FK "nullable; exactly-one scope via CHECK"
        uuid team_id FK "nullable"
        uuid service_id FK "nullable"
        text kind
        text status
        jsonb config
    }
```

Every source row satisfies `(org_id IS NOT NULL) + (team_id IS NOT NULL) +
(service_id IS NOT NULL) = 1` — enforced with a CHECK constraint in the
`sources` table.

### Documents and dependencies

- `kg_documents` holds denormalized `(source_id, org_id, team_id, service_id)`
  plus title/path/platform. Dropping a source cascades these away.
- `kg_dependencies` carries two edge flavours in one table. **Catalog edges**
  link `from_service_id` to `to_service_id` (both UUIDs in `services`).
  **External edges** set `to_service_id` NULL and use `to_external_name` +
  `to_external_description` to capture targets outside the declared catalog
  (Stripe, Auth0, an upstream team's API). A CHECK constraint enforces XOR;
  external uniqueness is case-insensitive via a function-based unique index
  on `(from_service_id, lower(to_external_name))`. Rows are user-managed via
  the service detail page — the ingestion pipeline does not write to this
  table. Edges carry `source = 'manual'` so any future automated origin can
  be distinguished. The org graph filters external rows out because the
  visualization only renders declared catalog nodes.
- `document_registry` keeps content-hash idempotency and gains `source_id`.

## Ingestion Flow

```mermaid
sequenceDiagram
    participant UI as Setup Wizard / Sources UI
    participant API as Catalog Routes
    participant Pipe as IngestionPipeline
    participant Conn as Connector (e.g. GitLab)
    participant Store as OpenSearch + Postgres
    participant Cat as Catalog Repos

    UI->>API: POST /api/sources {scope, scope_id, kind, config, token}
    API->>Cat: insert sources row + source_secrets
    UI->>API: POST /api/sources/{id}/ingest
    API->>Pipe: ingest_source(source_id, force)
    Pipe->>Cat: load source + resolve scope
    Pipe->>Conn: list_documents() / fetch_document()
    Pipe->>Pipe: parse → chunk → tag with scope → embed
    Pipe->>Store: bulk index chunks (with org_id, team_id, service_id)
    Pipe->>Cat: write kg_documents + document_registry
    Pipe-->>API: status: ready | error
```

## Product Surfaces

```mermaid
graph LR
    subgraph UI["PRISM UI (Port 5173)"]
        SETUP["/setup<br/>Create org · teams · services"]
        D["/<br/>Dashboard"]
        A["/analyze<br/>Structured intake · live run"]
        S["/search<br/>Scope-aware search"]
        C["/chat<br/>Grounded answers"]
        SO["/sources<br/>Declared sources list"]
        SDET["/sources/:id<br/>Sync · docs · status"]
        ORG["/orgs/:id · /teams/:id · /services/:id<br/>Declared entities"]
        H["/history<br/>Saved analyses"]
    end

    subgraph API["Backend Services"]
        CAT["Catalog APIs"]
        ANALYSIS["Analysis APIs"]
        SEARCHAPI["Search APIs"]
        CHATAPI["Chat APIs"]
    end

    SETUP --> CAT
    ORG --> CAT
    SO --> CAT
    SDET --> CAT
    D --> CAT
    A --> ANALYSIS
    S --> SEARCHAPI
    C --> CHATAPI
    H --> ANALYSIS

    classDef ui fill:#0f766e,color:#fff,stroke:none;
    classDef api fill:#2563eb,color:#fff,stroke:none;

    class SETUP,D,A,S,C,SO,SDET,ORG,H ui;
    class CAT,ANALYSIS,SEARCHAPI,CHATAPI api;
```

## Runtime Flows

### 1. Analysis Flow

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant ORC as Orchestrator
    participant RET as Retrieval
    participant RTR as Router
    participant DEP as Dependencies
    participant RSK as Risk + Effort
    participant COV as Coverage
    participant CIT as Citations
    participant SYN as Synthesis
    participant PG as PostgreSQL

    U->>API: POST /api/analyze
    API-->>U: analysis_id + stream URL
    U->>API: GET /api/analyze/{id}/stream

    API->>PG: create history row
    API->>ORC: run analysis
    ORC->>RET: retrieve relevant chunks
    ORC->>RTR: pick primary + supporting team(s)
    ORC->>DEP: map dependency edges from declared graph
    ORC->>RSK: assess risk + effort
    ORC->>COV: check gaps + stale evidence
    ORC->>CIT: verify claims against sources
    ORC->>SYN: build final report narrative
    ORC->>PG: persist completed report
    API-->>U: SSE complete event
```

### 2. Search Flow (scope-aware)

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant HS as Hybrid Search
    participant OS as OpenSearch

    U->>API: POST /api/search {query, filters, scope:{org_id, team_ids, service_ids}, page}
    API->>HS: retrieve ranked chunks with scope_filter
    HS->>OS: BM25 + vector search + scope bool-clauses
    OS-->>HS: ranked chunk hits
    HS-->>API: normalized result list
    API-->>U: paginated search response
```

## Data Responsibilities

| Store | Role |
|---|---|
| **Catalog tables** (`organizations`, `teams`, `services`, `sources`) | The authoritative declared ownership graph. All other writes reference these by UUID FK. |
| **OpenSearch** | Chunk storage, embeddings, hybrid retrieval, source preview lookup. Chunks carry `source_id`, `org_id`, `team_id`, `service_id` for filter pushdown. |
| **PostgreSQL / kg_documents** | One row per ingested document with scope pointers + source pointer. |
| **PostgreSQL / kg_dependencies** | User-managed service-to-service edges by UUID. Written by the service detail page UI, not by ingestion. |
| **PostgreSQL / document_registry** | Idempotency (content hash) + which source ingested each doc. |
| **PostgreSQL / analyses** | Analysis history + LangGraph checkpoints. Unchanged by Phase 1. |
| **Redis** | Present in local Docker stack as auxiliary infrastructure. |

## Deployment View

The default local stack uses Docker for infrastructure, `uvicorn` for the API
on `:8000`, and Vite for the UI on `:5173`. First boot drops the user at
`/setup` because the catalog starts empty. See [deployment.md](deployment.md)
for ports, env vars, and container details.
