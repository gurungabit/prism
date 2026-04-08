# Architecture

## System Topology

PRISM has two primary product paths:

- **Analysis** for long-running, multi-agent requirement briefs
- **Search and chat** for direct retrieval over the same knowledge base

```mermaid
graph TB
    subgraph CLIENT["Client Surfaces"]
        DASH["Dashboard"]
        ANALYZE["Analyze"]
        SEARCH["Search"]
        CHAT["Chat"]
        SOURCES["Sources"]
        HISTORY["History"]
    end

    subgraph API_LAYER["Application Layer"]
        API["FastAPI API<br/>Port 8000"]
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
        HS["Hybrid Search<br/>BM25 + vector"]
        RRK["Cross-encoder<br/>Reranker"]
        LLM["Ollama<br/>Qwen 2.5 7B"]
    end

    subgraph DATA["Data Stores"]
        OS[(OpenSearch)]
        N4J[(Neo4j)]
        PG[(PostgreSQL)]
    end

    DASH --> API
    ANALYZE --> API
    SEARCH --> API
    CHAT --> API
    SOURCES --> API
    HISTORY --> API
    API --> STREAM

    API --> ORC
    ORC --> RET --> RTR --> DEP --> RSK --> COV --> CIT --> SYN
    RET --> HS --> RRK
    HS --> OS
    RTR --> N4J
    DEP --> N4J
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

    class DASH,ANALYZE,SEARCH,CHAT,SOURCES,HISTORY client;
    class API,STREAM api;
    class ORC,RET,RTR,DEP,RSK,COV,CIT,SYN engine;
    class HS,RRK retrieval;
    class OS,N4J,PG data;
    class LLM ai;
```

## Product Surfaces

```mermaid
graph LR
    subgraph UI["PRISM UI (Port 5173)"]
        D["Dashboard<br/>Health · teams · conflicts"]
        A["Analyze<br/>Structured intake · live run view"]
        S["Search<br/>Filters · pagination · chunk previews"]
        C["Chat<br/>Grounded answers · citations"]
        SO["Sources<br/>Inventory · sync controls"]
        H["History<br/>Saved analyses"]
    end

    subgraph API["Backend Services"]
        ANALYSIS["Analysis APIs"]
        SEARCHAPI["Search APIs"]
        CHATAPI["Chat APIs"]
        SOURCEAPI["Sources + history APIs"]
    end

    D --> SOURCEAPI
    A --> ANALYSIS
    S --> SEARCHAPI
    C --> CHATAPI
    SO --> SOURCEAPI
    H --> SOURCEAPI

    classDef ui fill:#0f766e,color:#fff,stroke:none;
    classDef api fill:#2563eb,color:#fff,stroke:none;

    class D,A,S,C,SO,H ui;
    class ANALYSIS,SEARCHAPI,CHATAPI,SOURCEAPI api;
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
    ORC->>RTR: choose owner + services in scope
    ORC->>DEP: map dependency edges
    ORC->>RSK: assess risk + effort
    ORC->>COV: check gaps + stale evidence
    ORC->>CIT: verify claims against sources
    ORC->>SYN: build final report narrative
    ORC->>PG: persist completed report
    API-->>U: SSE complete event
```

### 2. Search Flow

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant HS as Hybrid Search
    participant OS as OpenSearch

    U->>API: POST /api/search {query, filters, page, page_size}
    API->>HS: retrieve ranked chunks
    HS->>OS: BM25 + vector search
    OS-->>HS: ranked chunk hits
    HS-->>API: normalized result list
    API-->>U: paginated search response
```

### 3. Chat Flow

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant HS as Hybrid Search
    participant LLM as Ollama

    U->>API: POST /api/chat
    API->>HS: retrieve top supporting chunks
    API-->>U: SSE metadata with citations
    API->>LLM: grounded prompt with retrieved chunks
    LLM-->>API: streamed answer tokens
    API-->>U: token events + done
```

## Layer Breakdown

```mermaid
graph LR
    subgraph L0["Layer 0 · Source Systems"]
        GL["GitLab"]
        SP["SharePoint"]
        EX["Excel / CSV"]
        ON["OneNote"]
    end

    subgraph L1["Layer 1 · Ingestion"]
        P["Parser"]
        CH["Chunker"]
        DD["Deduplicator"]
        EM["Embedder"]
        IX["Indexer"]
        EE["Entity Extraction"]
        GB["Graph Builder"]
    end

    subgraph L2["Layer 2 · Retrieval"]
        QE["Query Expansion"]
        BM["BM25 + Vector Search"]
        RF["RRF Fusion"]
        RR["Cross-encoder Rerank"]
    end

    subgraph L3["Layer 3 · Reasoning"]
        AG["Specialist Agents"]
    end

    subgraph L4["Layer 4 · Delivery"]
        FA["FastAPI Routes"]
        ST["SSE Streaming"]
    end

    subgraph L5["Layer 5 · Experience"]
        UI["React UI"]
    end

    GL --> P
    SP --> P
    EX --> P
    ON --> P
    P --> CH --> DD --> EM --> IX
    CH --> EE --> GB
    QE --> BM --> RF --> RR --> AG
    AG --> FA --> ST --> UI

    classDef source fill:#64748b,color:#fff,stroke:none;
    classDef ingest fill:#0f766e,color:#fff,stroke:none;
    classDef retrieval fill:#7c3aed,color:#fff,stroke:none;
    classDef reasoning fill:#f59e0b,color:#fff,stroke:none;
    classDef delivery fill:#2563eb,color:#fff,stroke:none;
    classDef experience fill:#0891b2,color:#fff,stroke:none;

    class GL,SP,EX,ON source;
    class P,CH,DD,EM,IX,EE,GB ingest;
    class QE,BM,RF,RR retrieval;
    class AG reasoning;
    class FA,ST delivery;
    class UI experience;
```

## Data Responsibilities

| Store | Role |
|---|---|
| OpenSearch | Chunk storage, embeddings, hybrid retrieval, source preview lookup |
| Neo4j | Teams, services, ownership, dependency relationships, conflicts |
| PostgreSQL | Document registry, analysis history, LangGraph checkpoints |
| Redis | Present in local Docker stack as auxiliary infrastructure, not part of the main request path documented above |

## Knowledge Graph Schema

```mermaid
graph LR
    T((Team))
    S((Service))
    D((Document))
    P((Person))
    TH((Technology))

    T -->|OWNS| S
    T -->|MAINTAINS| D
    S -->|DEPENDS_ON| S
    S -->|USES| TH
    P -->|BELONGS_TO| T
    P -->|AUTHORED| D
    D -->|REFERENCES| S

    classDef team fill:#0f766e,color:#fff,stroke:none;
    classDef service fill:#2563eb,color:#fff,stroke:none;
    classDef doc fill:#7c3aed,color:#fff,stroke:none;
    classDef person fill:#f59e0b,color:#fff,stroke:none;
    classDef tech fill:#64748b,color:#fff,stroke:none;

    class T team;
    class S service;
    class D doc;
    class P person;
    class TH tech;
```

### Core Node Properties

| Node | Typical properties |
|---|---|
| Team | `name`, `description`, `contact` |
| Service | `name`, `team_owner`, `status`, `repo_url` |
| Document | `id`, `title`, `path`, `platform`, `last_modified` |
| Person | `name`, `email`, `team` |
| Technology | `name`, `version` |

### Core Edge Properties

| Edge | Typical properties |
|---|---|
| `OWNS` | `confidence`, `source`, `last_updated` |
| `DEPENDS_ON` | `source`, `confidence`, `reason` |
| `MAINTAINS` | `source` |

## Deployment View

The default local stack uses Docker for infrastructure, `uvicorn` for the API on `:8000`, and Vite for the UI on `:5173`. See [deployment.md](deployment.md) for ports, env vars, and container details.
