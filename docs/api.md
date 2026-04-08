# API Reference

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

## Analysis

### Start Analysis

```http
POST /api/analyze
```

Request body:

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

Only `requirement` is required. The remaining fields are optional but improve retrieval and agent quality.

Response:

```json
{
  "analysis_id": "a1b2c3d4-...",
  "stream_url": "/api/analyze/a1b2c3d4-.../stream"
}
```

### Stream Analysis

```http
GET /api/analyze/{analysis_id}/stream
```

Server-Sent Events stream. Supports `Last-Event-ID` for reconnection.

Typical events:

```json
{
  "type": "agent_step",
  "id": "a1b2c3d4-000003",
  "agent": "router",
  "action": "reasoning",
  "detail": "AI is analyzing...",
  "timestamp": 1712100000.0
}
```

```json
{
  "type": "complete",
  "id": "a1b2c3d4-000042",
  "report": { "...PRISMReport..." },
  "timestamp": 1712100045.0
}
```

```json
{
  "type": "error",
  "id": "a1b2c3d4-000010",
  "error": "Analysis failed: ...",
  "timestamp": 1712100010.0
}
```

### Get Report

```http
GET /api/analyze/{analysis_id}/report
```

Responses:

- `200`: completed report
- `202`: analysis is still running
- `404`: unknown analysis
- `500`: analysis failed

### Get Trace

```http
GET /api/analyze/{analysis_id}/trace
```

Returns the stored event stream for the run.

### Get Sources For Analysis

```http
GET /api/analyze/{analysis_id}/sources
```

Returns source documents referenced by the completed report.

### Submit Feedback

```http
POST /api/analyze/{analysis_id}/feedback
```

```json
{
  "section": "team_routing",
  "correct_answer": "Security Team",
  "reason": "Recent reorg moved auth-service ownership"
}
```

## Search

### Manual Search

```http
POST /api/search
```

Request body:

```json
{
  "query": "authentication service architecture",
  "filters": {
    "source_platform": "gitlab",
    "doc_type": ["wiki", "readme"],
    "team_hint": ["Platform Team"],
    "service_hint": ["auth-service"]
  },
  "page": 1,
  "page_size": 40
}
```

Notes:

- `page_size` defaults to `40`
- `top_k` is also accepted and is treated as the requested page size
- filters are passed through to retrieval; values may be single strings or arrays

Response:

```json
{
  "query": "authentication service architecture",
  "results": [
    {
      "chunk_id": "chunk-123",
      "content": "Auth service handles login and MFA challenges...",
      "score": 0.941,
      "source_path": "platform-team/auth-service/wiki/architecture.md",
      "document_title": "Auth Service Architecture",
      "doc_type": "wiki",
      "platform": "gitlab"
    }
  ],
  "page": 1,
  "page_size": 40,
  "has_more": true,
  "total": 67
}
```

## Chat

### Start Or Continue Chat

```http
POST /api/chat
```

Request body:

```json
{
  "message": "What teams own the checkout service?",
  "conversation_id": "optional-existing-id"
}
```

Response is an SSE stream with events:

- `metadata`: conversation id and retrieved citations
- `token`: streamed answer text
- `done`: terminal event for the message

Example metadata payload:

```json
{
  "conversation_id": "conv-123",
  "citations": [
    {
      "index": 1,
      "source_path": "payments-team/team-charter.md",
      "source_url": "",
      "platform": "sharepoint",
      "title": "Team Charter",
      "section_heading": "",
      "score": 0.83,
      "content": "The Payments Team is responsible for...",
      "excerpt": "The Payments Team is responsible for..."
    }
  ]
}
```

Notes:

- Chat is retrieval-grounded and currently uses in-memory conversation storage
- Conversations do not survive API restarts

### List Conversations

```http
GET /api/chat/conversations
```

### Get Conversation

```http
GET /api/chat/{conversation_id}
```

### Delete Conversation

```http
DELETE /api/chat/{conversation_id}
```

### Get Source Preview For Chat Citation

```http
GET /api/chat/source-preview/by-path?source_path=payments-team/team-charter.md&source_platform=sharepoint
```

Returns the earliest matching chunk for a cited document so the UI can show a chunk preview popup for chat citations.

## Sources

### List Ingested Sources

```http
GET /api/sources
```

Response groups documents by platform and includes:

- `platform`
- `document_count`
- `last_ingested`
- `documents[]`

Each document entry includes:

- `document_id`
- `source_path`
- `chunk_count`
- `status`
- `last_ingested_at`

## History

### List Analysis History

```http
GET /api/history?limit=20&offset=0
```

### Delete Analysis History Entry

```http
DELETE /api/history/{analysis_id}
```

## Ingestion

### Trigger Incremental Ingestion

```http
POST /api/ingest
POST /api/ingest?force=true
```

### Ingest One Platform

```http
POST /api/ingest/{platform}
```

Supported platforms in the seed dataset:

- `gitlab`
- `sharepoint`
- `excel`
- `onenote`

### Force Full Re-index

```http
POST /api/ingest/full
```

## Knowledge Graph

### List Teams

```http
GET /api/graph/teams
```

### Get Team Profile

```http
GET /api/graph/teams/{team_name}
```

### Get Service Info

```http
GET /api/graph/services/{service_name}
```

Returns the service, current owners, and dependencies.

### Get Service Dependencies

```http
GET /api/graph/dependencies/{service_name}?depth=2
```

### List Ownership Conflicts

```http
GET /api/graph/conflicts
```

## Health

```http
GET /api/health
```

```json
{
  "status": "healthy",
  "service": "prism-api"
}
```

## Report Shape

Completed analyses return a `PRISMReport`. Important top-level fields include:

```json
{
  "analysis_id": "uuid",
  "requirement": "Add MFA to customer portal",
  "analysis_input": {
    "requirement": "Add MFA to customer portal",
    "business_goal": "",
    "context": "",
    "constraints": "",
    "known_teams": "",
    "known_services": "",
    "questions_to_answer": ""
  },
  "created_at": "2026-04-08T18:30:00Z",
  "duration_seconds": 45.2,
  "executive_summary": "...",
  "recommendations": ["..."],
  "team_routing": { "...": "..." },
  "affected_services": [{ "...": "..." }],
  "dependencies": {
    "blocking": [],
    "impacted": [],
    "informational": []
  },
  "risk_assessment": { "...": "..." },
  "effort_estimate": { "...": "..." },
  "coverage_report": {
    "documents_retrieved": 30,
    "documents_cited": 5,
    "critical_gaps": [],
    "stale_sources": []
  },
  "verification_report": {
    "verified_claims": [],
    "unsupported_claims": [],
    "stale_source_warnings": []
  },
  "impact_matrix": [],
  "all_sources": []
}
```

UI terminology note:

- `affected_services` is rendered as **Services In Scope**
- dependency lists are rendered as **Blocking**, **Non-Blocking**, and **Contextual** dependencies in the UI
