# Data Flow

## Ingestion Pipeline

```mermaid
graph LR
    subgraph SRC["Source Connectors"]
        GL["GitLab"]
        SP["SharePoint"]
        EX["Excel / CSV"]
        ON["OneNote"]
    end

    subgraph PARSE["Parsing"]
        P["Parser"]
        FT["Markdown · JSON · HTML<br/>DOCX · PDF · Excel · CSV"]
    end

    subgraph PROC["Processing"]
        CH["Chunker"]
        DD["Deduplicator"]
        EM["Embedder"]
        EE["Entity Extraction"]
        TN["Team Sanitization"]
    end

    subgraph STORE["Storage"]
        OS[(OpenSearch)]
        N4J[(Neo4j)]
        PG[(PostgreSQL Registry)]
    end

    GL --> P
    SP --> P
    EX --> P
    ON --> P
    P --> FT --> CH --> DD --> EM --> OS
    CH --> EE --> TN --> N4J
    DD --> PG

    classDef source fill:#64748b,color:#fff,stroke:none;
    classDef parse fill:#0f766e,color:#fff,stroke:none;
    classDef proc fill:#f59e0b,color:#fff,stroke:none;
    classDef store fill:#4f46e5,color:#fff,stroke:none;

    class GL,SP,EX,ON source;
    class P,FT parse;
    class CH,DD,EM,EE,TN proc;
    class OS,N4J,PG store;
```

## Incremental Ingestion

```mermaid
flowchart TD
    START[Document discovered] --> HASH[Compute content hash]
    HASH --> CHECK{Already in registry?}
    CHECK -->|no| NEW[mark as new]
    CHECK -->|yes| COMPARE{Hash changed?}
    COMPARE -->|no| SKIP[skip unchanged document]
    COMPARE -->|yes| UPDATE[remove old chunks + graph edges]
    NEW --> PROCESS[parse, chunk, embed, index, graph]
    UPDATE --> PROCESS
    PROCESS --> REG[update PostgreSQL registry]
    SKIP --> DONE[done]
    REG --> DONE
```

## Chunk Metadata

Each chunk indexed in OpenSearch carries document and entity hints used by search, chat, and agents.

```text
chunk_id
document_id
content
embedding
source_platform
source_path
source_url
document_title
section_heading
team_hint
service_hint
doc_type
last_modified
author
chunk_index
total_chunks
canonical_chunk_id
```

## Retrieval Pipeline

PRISM uses the same hybrid retrieval engine for:

- analysis retrieval
- manual search
- chat grounding
- chat source preview fallback

```mermaid
graph LR
    REQ["Query / Requirement Brief"] --> QE["Query Expansion"]
    QE --> BM25["BM25 Retrieval"]
    QE --> VEC["Vector Retrieval"]
    BM25 --> RRF["RRF Fusion"]
    VEC --> RRF
    RRF --> DEDUP["Deduplicate"]
    DEDUP --> TOP["Top-K Candidates"]
    TOP --> RR["Task-specific Rerank"]

    classDef input fill:#0f766e,color:#fff,stroke:none;
    classDef retrieval fill:#7c3aed,color:#fff,stroke:none;
    classDef process fill:#f59e0b,color:#fff,stroke:none;

    class REQ input;
    class QE,BM25,VEC,RRF retrieval;
    class DEDUP,TOP,RR process;
```

### Analysis Retrieval

- query can be built from `requirement`, `business_goal`, `context`, `constraints`, `known_teams`, `known_services`, and `questions_to_answer`
- reranking is specialized by downstream agent
- coverage may trigger another retrieval round if critical gaps remain

### Manual Search

- uses the same hybrid engine without LLM query expansion
- supports server-side pagination
- supports filters such as `doc_type`, `team_hint`, `service_hint`, and `source_platform`

### Chat Retrieval

- retrieves a focused set of supporting chunks
- sends citation metadata to the UI before answer tokens stream
- can later fetch a source preview by `source_path` for citation popups

## Hybrid Search Details

### BM25

- exact text matching on chunk content
- good for names, ticket ids, acronyms, and explicit service references

### Vector Search

- semantic nearest-neighbor search over embeddings
- good for concept-level retrieval when wording differs

### Reciprocal Rank Fusion

```text
RRF score(doc) = sum(1 / (k + rank))
k = 60
```

### Re-ranking

Cross-encoder reranking is applied after fusion to tailor the final evidence set to the task.

| Consumer | Typical focus |
|---|---|
| Router | ownership docs, readmes, architecture, service catalogs |
| Dependencies | readmes, runbooks, architecture, issues |
| Risk + effort | incidents, issues, runbooks, meeting notes |
| Search UI | raw retrieval order, paginated |
| Chat | top supporting chunks for grounded answer generation |

## Entity Extraction

During ingestion, PRISM extracts teams, services, and relationships to populate Neo4j.

```mermaid
graph TD
    DOC["Parsed Document"] --> TRY{"Ollama available?"}
    TRY -->|yes| LLM["LLM Extraction"]
    TRY -->|no| FALLBACK["Deterministic Fallback"]
    LLM -->|success| NORMALIZE["Normalize + Sanitize"]
    LLM -->|failure| FALLBACK
    FALLBACK --> NORMALIZE
    NORMALIZE --> TEAM["Canonical Team Names"]
    NORMALIZE --> SVC["Service Names"]
    NORMALIZE --> EDGES["Ownership + Dependency Edges"]

    classDef doc fill:#64748b,color:#fff,stroke:none;
    classDef ai fill:#e11d48,color:#fff,stroke:none;
    classDef process fill:#f59e0b,color:#fff,stroke:none;
    classDef output fill:#2563eb,color:#fff,stroke:none;

    class DOC doc;
    class LLM,FALLBACK ai;
    class TRY,NORMALIZE process;
    class TEAM,SVC,EDGES output;
```

Important current behavior:

- team extraction is no longer a loose catch-all regex
- explicit team signals are normalized and sanitized to avoid junk nodes like `See Team` or `At Team`
- path-based team aliases such as `payments-team` are reconciled into canonical names like `Payments Team`

## Conflict Detection

When multiple teams claim the same service, PRISM keeps both claims and lets the analysis surface the ambiguity.

```mermaid
graph LR
    T1["Platform Team"] -->|OWNS| S["auth-service"]
    T2["Security Team"] -->|OWNS| S
    S --> C["Conflict preserved"]
    C --> R["Router explains confidence<br/>and ownership ambiguity"]

    classDef team fill:#0f766e,color:#fff,stroke:none;
    classDef service fill:#2563eb,color:#fff,stroke:none;
    classDef warn fill:#d97706,color:#fff,stroke:none;

    class T1,T2 team;
    class S service;
    class C,R warn;
```
