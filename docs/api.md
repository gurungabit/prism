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

### Get Sources For Analysis

```http
GET /api/analyze/{analysis_id}/sources
```

### Submit Feedback

```http
POST /api/analyze/{analysis_id}/feedback
```

## Search

### Manual Search (scope-aware)

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
  "scope": {
    "org_id": "11111111-1111-1111-1111-111111111111",
    "team_ids": ["22222222-2222-2222-2222-222222222222"],
    "service_ids": ["33333333-3333-3333-3333-333333333333"]
  },
  "page": 1,
  "page_size": 40
}
```

Notes:

- `scope` is optional. If present it pushes down to OpenSearch. Org-scoped
  chunks always match; team/service chunks match only when in scope (or when
  they carry NULL for that level).
- `filters` are the regular text/keyword field filters (platform, doc type,
  legacy team/service hints).

Response:

```json
{
  "query": "authentication service architecture",
  "results": [
    {
      "chunk_id": "chunk-123",
      "content": "Auth service handles login and MFA challenges...",
      "score": 0.941,
      "source_path": "platform-team/auth-service@main:docs/architecture.md",
      "document_title": "Auth Service Architecture",
      "doc_type": "wiki",
      "platform": "gitlab",
      "org_id": "11111111-1111-1111-1111-111111111111",
      "team_id": "22222222-2222-2222-2222-222222222222",
      "service_id": "33333333-3333-3333-3333-333333333333"
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

### List / Get / Delete Conversation

```http
GET    /api/chat/conversations
GET    /api/chat/{conversation_id}
DELETE /api/chat/{conversation_id}
```

### Source Preview

```http
GET /api/chat/source-preview/by-path?source_path=...&source_platform=gitlab
```

## Catalog (declarative ownership model)

### Organizations

```http
POST   /api/orgs                              { "name": "Acme" }
GET    /api/orgs
GET    /api/orgs/{org_id}
PATCH  /api/orgs/{org_id}                     { "name": "Acme Engineering" }
DELETE /api/orgs/{org_id}
```

### Teams

```http
POST   /api/orgs/{org_id}/teams               { "name": "Platform", "description": "..." }
GET    /api/orgs/{org_id}/teams
GET    /api/teams/{team_id}
PATCH  /api/teams/{team_id}                   { "name": "...", "description": "..." }
DELETE /api/teams/{team_id}
```

### Services

```http
POST   /api/teams/{team_id}/services          { "name": "auth-service", "repo_url": "...", "description": "..." }
GET    /api/teams/{team_id}/services
GET    /api/services/{service_id}
PATCH  /api/services/{service_id}              { "name": "...", "repo_url": "...", "description": "..." }
DELETE /api/services/{service_id}
```

### Service dependencies (manual)

Edges are user-managed. The "Dependencies" section on a service detail page
talks to these endpoints:

```http
GET    /api/services/{service_id}/dependencies
POST   /api/services/{service_id}/dependencies
DELETE /api/services/{service_id}/dependencies/{to_service_id}
DELETE /api/services/{service_id}/dependencies/external?name={external_name}
```

POST body — exactly one of `to_service_id` (catalog edge) or
`to_external_name` (free-text target outside the catalog):

```json
{ "to_service_id": "uuid" }
```

```json
{ "to_external_name": "Stripe API",
  "to_external_description": "Payment intents (used by /checkout)" }
```

`to_external_name` is capped at 200 chars, `to_external_description` at
2000. Names dedupe case-insensitively at the DB layer (a UI client trying
to add `Stripe` after `stripe` updates the existing description in place
rather than creating a second row). External dedup is enforced by a
function-based unique index on `(from_service_id, lower(to_external_name))`.

The API rejects self-edges (`400`), bodies that pass both or neither
target field (`400`), unknown source/target services (`404`), and noops on
duplicate edges. New edges get `source = 'manual'`. The org graph
endpoint (`/api/organization/graph`) reads the same `kg_dependencies`
table but excludes external rows because the graph only renders declared
catalog nodes — external deps are visible only on the originating
service's detail page.

External-edge deletion uses a query parameter instead of a path segment
so target names containing `/`, `?`, or `#` (e.g. `Twilio SMS / Voice`)
don't break route matching. Matching is case-insensitive.

## Sources

### List / Get

```http
GET    /api/sources?org_id=&team_id=&service_id=
GET    /api/sources/{source_id}
GET    /api/sources/{source_id}/status
```

Response shape (list):

```json
{
  "sources": [
    {
      "id": "uuid",
      "org_id": null,
      "team_id": "uuid",
      "service_id": null,
      "kind": "gitlab",
      "name": "Platform Team GitLab",
      "config": { "group_path": "platform-team" },
      "status": "ready",
      "last_ingested_at": "2026-04-20T12:00:00Z",
      "document_count": 87,
      "created_at": "..."
    }
  ],
  "total": 1
}
```

### Create

```http
POST /api/sources
```

```json
{
  "scope": "team",
  "scope_id": "22222222-2222-2222-2222-222222222222",
  "kind": "gitlab",
  "name": "Platform Team GitLab",
  "config": { "group_path": "platform-team", "include_subgroups": true }
}
```

`scope` is `org` | `team` | `service`. The source row enforces exactly one
scope via a CHECK constraint.

For the GitLab connector, `config` is one of:

```json
{ "kind": "gitlab", "group_path": "platform-team", "include_subgroups": true }
```

```json
{ "kind": "gitlab", "project_path": "platform-team/api-gateway", "ref": "main", "include_wiki": true }
```

Optional config keys:

- `base_url` — overrides the default GitLab API endpoint (for self-hosted
  instances). Global default comes from `PRISM_GITLAB_BASE_URL`.
- `include_wiki` (default `true`) — toggles wiki page ingestion. Wiki pages
  come through the GitLab wiki API and are stored alongside repo files.
- `include_subgroups` (group mode, default `true`) — recurse into nested
  subgroups when listing projects.

The optional `token` field is still accepted for per-source overrides, but
the typical deploy uses the server-wide `PRISM_GITLAB_TOKEN` env var
instead — the wizard no longer collects a token.

#### Token policy

- **Default path**: server-side `PRISM_GITLAB_TOKEN` (a service-account
  PAT) is the canonical credential. Set it once at deploy time; every
  source request, validate call, and autocomplete query falls back to it
  when no per-source token is provided.
- **Per-source override**: the `token` field on `POST /api/sources` /
  `PATCH /api/sources/{id}` is preserved as an admin escape hatch (e.g.
  cross-tenant pulls where the service account doesn't have access). The
  public UI does **not** collect it; the only way to set one today is a
  direct API call.
- **Autocomplete routes** (`/api/gitlab/{projects,groups}/search`)
  similarly accept a request-body `token` for the admin override flow
  but normally use the server-side token. Tokens passed inline are
  used for that one round-trip and never persisted.
- **Auth gate**: PRISM is single-tenant in the current POC posture — the
  routes above are unauthenticated. Once auth lands (see
  AGENTS.md), per-source token submission should be admin-gated and
  redacted in logs / API responses.

### Update / Delete

```http
PATCH  /api/sources/{source_id}               { "name": "...", "config": { ... }, "token": "..." }
DELETE /api/sources/{source_id}
```

Passing `"token": ""` in an update *clears* the stored secret. Omitting
`token` leaves it unchanged.

Deleting a source removes its OpenSearch chunks first, then cascades
through Postgres (`kg_documents`, `document_registry`, `source_secrets`).
If the OpenSearch cleanup step fails the route returns **503** and
keeps the source row intact, so the operator (or a future durable
retry worker) can try again once OpenSearch is healthy. Org / team /
service deletes follow the same abort-on-OS-failure pattern for any
descendant sources they cascade through.

### Ingest

```http
POST /api/sources/{source_id}/ingest
POST /api/sources/{source_id}/ingest?force=true
```

Returns `{ "status": "started", "source_id": "...", "force": false }`
immediately; ingestion runs as a background task. Poll
`/api/sources/{id}/status` for progress.

`force=true` wipes the source's existing chunks and re-ingests every
document (ignoring content-hash caching).

### Validate (test connection)

```http
POST /api/sources/validate
```

```json
{
  "kind": "gitlab",
  "config": { "project_path": "platform-team/api-gateway" }
}
```

Used by the "Test connection" button in the source wizard. For GitLab it
hits `/projects/:path` against the server-side token and returns the
resolved project(s). For path-based connectors it checks the local path
exists.

### GitLab project + group autocomplete

The wizard's project / group dropdowns proxy through the API rather than
hitting GitLab from the browser:

```http
POST /api/gitlab/projects/search    { "q": "frontend", "page": 1, "per_page": 20 }
POST /api/gitlab/groups/search      { "q": "platform", "page": 1, "per_page": 20 }
```

Both use the server-side token (or the one passed in the body) and scope to
membership-only when authenticated. Responses include `has_more` (next-page
hint) so the picker can load more on scroll.

## Threads (multi-turn analyses)

```http
GET /api/threads/{thread_id_or_run_id}
```

Returns every turn in a thread oldest-first. Each turn carries:

- `requirement` — what the user typed
- `title` — 4-8 word headline generated by the planner (LLM); empty until
  the title task lands
- `kind` — `pending` | `full` | `chat`
- `rolling_summary` — one-paragraph memo from a completed run, used as
  context for future follow-ups

## Knowledge Graph (catalog-backed) — legacy

> **Compatibility surface, name-based.** These routes predate the
> UUID-keyed catalog and look services / teams up by *name*. Service
> names are team-scoped (and team names are org-scoped), so a name
> like `auth-service` can resolve to different services across teams /
> orgs in a multi-tenant catalog. They're kept for now because the
> dependency agent and a couple of older UI views still call them, but
> **new frontend code should use the UUID-keyed
> `/api/orgs/{org_id}/teams`, `/api/teams/{team_id}/services`,
> `/api/services/{service_id}`, and `/api/services/{service_id}/dependencies`
> instead.** These will be removed once nothing internal calls them.

### List Teams

```http
GET /api/graph/teams
```

Returns declared teams with owned service names. Always backed by the
catalog now — no more inference.

### Get Team Profile / Service / Dependencies

```http
GET /api/graph/teams/{team_name}
GET /api/graph/services/{service_name}
GET /api/graph/dependencies/{service_name}?depth=2
```

Returns the first match for the name. In ambiguous cases (same service
name in two teams) you'll get an arbitrary winner — prefer the UUID
routes when correctness matters.

**Removed**: `GET /api/graph/conflicts`. Under the declared model a service
belongs to exactly one team, so ownership conflicts are not possible at
the data layer (see plan open question 4).

**Removed**: `POST /api/ingest`, `POST /api/ingest/{platform}`,
`POST /api/ingest/full`. These legacy endpoints assumed the seed-data
layout; use `POST /api/sources/{id}/ingest` instead.

## History

```http
GET    /api/history?limit=20&offset=0
DELETE /api/history/{analysis_id}
```

## Health

```http
GET /api/health
```

```json
{ "status": "healthy", "service": "prism-api" }
```

## Report Shape

Completed analyses return a `PRISMReport`. Important top-level fields
include:

```json
{
  "analysis_id": "uuid",
  "requirement": "Add MFA to customer portal",
  "analysis_input": { "...": "..." },
  "created_at": "2026-04-20T18:30:00Z",
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
- dependency lists are rendered as **Blocking**, **Non-Blocking**, and
  **Contextual** dependencies in the UI
