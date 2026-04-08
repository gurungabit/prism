# Agent System

## Orchestrator Overview

PRISM runs a LangGraph workflow with PostgreSQL checkpointing. The pipeline is mostly linear, with one bounded retrieval loop triggered by the coverage agent when critical evidence gaps remain.

```mermaid
flowchart LR
    R["Retrieve"]
    RT["Route"]
    D["Dependencies"]
    RE["Risk + Effort"]
    C["Coverage"]
    CI["Citations"]
    S["Synthesis"]

    R --> RT --> D --> RE --> C --> CI --> S
    C -. retry when critical gaps remain .-> R

    classDef step fill:#f59e0b,color:#fff,stroke:none;
    class R,RT,D,RE,C,CI,S step;
```

## Agent Roster

```mermaid
graph TB
    subgraph FLOW["LangGraph Workflow"]
        R["Retrieval"]
        RT["Router"]
        D["Dependencies"]
        RE["Risk + Effort"]
        C["Coverage"]
        CI["Citations"]
        S["Synthesis"]
    end

    subgraph SHARED["Shared Resources"]
        OS[(OpenSearch)]
        N4J[(Neo4j)]
        RRK["Cross-encoder<br/>Reranker"]
        LLM["Ollama<br/>Qwen 2.5 7B"]
    end

    R --> RT --> D --> RE --> C --> CI --> S
    C -. bounded retry .-> R

    R --> OS
    R --> RRK
    RT --> N4J
    RT --> LLM
    D --> N4J
    D --> LLM
    RE --> LLM
    C --> LLM
    CI --> LLM
    S --> LLM

    classDef flow fill:#f59e0b,color:#fff,stroke:none;
    classDef store fill:#4f46e5,color:#fff,stroke:none;
    classDef ai fill:#e11d48,color:#fff,stroke:none;

    class R,RT,D,RE,C,CI,S flow;
    class OS,N4J,RRK store;
    class LLM ai;
```

## Agent Responsibilities

### Retrieval

Purpose:
- retrieve the most relevant chunks for the requirement brief
- expand the query when LLM support is available
- provide a shared evidence set to downstream agents

Key behaviors:
- hybrid retrieval over OpenSearch
- de-duplication by canonical chunk id
- graceful degradation if evidence is sparse

### Router

Purpose:
- recommend a primary owner and supporting teams
- identify the **services in scope** for the requirement

Key behaviors:
- reranks routing-relevant chunks
- queries Neo4j for teams, service ownership, and conflicts
- uses the LLM to score candidate teams and explain the recommendation

Notes:
- the UI presents router services as **Services In Scope**
- ownership conflicts are preserved and surfaced instead of silently resolved

### Dependencies

Purpose:
- map service-to-service relationships around the work

Key behaviors:
- prefers router-identified services in scope
- falls back to chunk service hints only when routing did not identify services
- traverses Neo4j dependencies and classifies edges

Output semantics:
- `blocking`: relationships that are likely to stop or gate the work
- `impacted`: non-blocking edges affected by the work
- `informational`: contextual edges that help explain the system

UI labels:
- `impacted` is rendered as **Non-Blocking Dependencies**
- `informational` is rendered as **Contextual Dependencies**

### Risk + Effort

Purpose:
- assess implementation risk and estimate effort

Key behaviors:
- reranks risk-relevant evidence
- detects stale documents
- generates categorized risk items and staffing/effort ranges

Risk categories:
- `technical_complexity`
- `dependency_risk`
- `knowledge_gaps`
- `integration_risk`
- `data_risk`
- `security_risk`

### Coverage

Purpose:
- determine whether the analysis is sufficiently supported by documentation

Key behaviors:
- checks whether identified services have supporting docs
- tracks critical gaps and stale sources
- can trigger one or more bounded retrieval retries

### Citations

Purpose:
- verify claims and surface unsupported conclusions

Key behaviors:
- compiles claims from upstream agent outputs
- ties verified claims to supporting documents and excerpts
- records unsupported claims and stale-source warnings

### Synthesis

Purpose:
- produce the final business-facing report

Key behaviors:
- combines all agent outputs into the executive summary and narratives
- includes recommendations, caveats, data-quality notes, verification results, and impact matrix rows

## Shared State

The orchestrator passes checkpoint-safe state between nodes. Non-serializable runtime values, such as step callbacks, are kept out of checkpointed state.

```mermaid
classDiagram
    class OrchestratorState {
        +str requirement
        +str analysis_id
        +str analysis_brief
        +dict analysis_input
        +list retrieved_chunks
        +AgentResult team_routing
        +AgentResult dependencies
        +AgentResult risk_assessment
        +AgentResult coverage_report
        +AgentResult citation_result
        +list stale_sources
        +list conflicts
        +int retrieval_rounds
        +list agent_trace
        +dict final_report
    }

    class AgentResult {
        +str status
        +Any data
        +str error
        +str degradation_note
    }
```

`AgentResult.status` is one of:

- `success`
- `partial`
- `failed`

## Graceful Degradation

```mermaid
flowchart TD
    A["Agent execution"] --> B{"Result status"}
    B -->|success| C["Full output"]
    B -->|partial| D["Reduced-confidence output<br/>with degradation note"]
    B -->|failed| E["Error recorded<br/>downstream continues"]
    C --> N["Next node"]
    D --> N
    E --> N
    N --> S["Synthesis calls out limitations<br/>in the final report"]

    classDef neutral fill:#334155,color:#fff,stroke:none;
    classDef good fill:#0f766e,color:#fff,stroke:none;
    classDef warn fill:#d97706,color:#fff,stroke:none;
    classDef bad fill:#dc2626,color:#fff,stroke:none;

    class A,B,N,S neutral;
    class C good;
    class D warn;
    class E bad;
```

## Prompting Pattern

Every specialist agent follows the same general structure:

1. system prompt defining role and hard rules
2. structured user prompt with requirement brief, retrieved chunks, and graph context
3. JSON schema constrained output validated with Pydantic

If parsing or validation fails, the orchestrator still returns a structurally valid partial result so the overall run can continue.
