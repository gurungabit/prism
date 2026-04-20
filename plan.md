# PRISM — Declarative Ownership Plan

## Goal

Replace today's regex-inferred ownership and pre-baked seed data with a declared **Org → Team → Service** hierarchy. Sources are attached at any of those three scopes. Ingestion produces documents that inherit their scope from the source, so retrieval can filter precisely without LLM extraction or path heuristics.

## Why

Today's pipeline tries to *guess* who owns what by parsing folder paths (`*-team/`) and document text (`Owned by: …`). The dashboard shows 8 teams and 0 services because the regex fallback never links teams to services, and the LLM extractor is wired up but never called. With real GitLab data this approach won't scale — group structure varies, naming is inconsistent, and document phrasing is unreliable.

A declared model trades onboarding friction for trustworthy data: someone has to set up the Org/Teams/Services up front, but every chunk thereafter has known provenance.

## Target Model

```
Organization
 ├── Sources (scope = org)              ← visible to every team in the org
 └── Teams
      ├── Sources (scope = team)        ← visible only to this team's analyses
      └── Services
           └── Sources (scope = service) ← narrowest; the service's own docs/repo
```

Every ingested document carries denormalized `(org_id, team_id, service_id)` columns. `team_id` and `service_id` are nullable depending on scope. Org docs always match retrieval; team and service docs match only when in scope.

## Schema Deltas

### New tables

```sql
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE teams (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);

CREATE TABLE services (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    repo_url    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, name)
);

CREATE TABLE sources (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID REFERENCES organizations(id) ON DELETE CASCADE,
    team_id           UUID REFERENCES teams(id) ON DELETE CASCADE,
    service_id        UUID REFERENCES services(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL,            -- 'gitlab' | 'sharepoint' | 'excel' | 'onenote'
    name              TEXT NOT NULL,            -- display name
    config            JSONB NOT NULL,           -- connector-specific (group_path, project_id, …)
    secret_ref        TEXT,                     -- pointer to a stored token (not the token itself)
    status            TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'syncing'|'ready'|'error'
    last_ingested_at  TIMESTAMPTZ,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (org_id     IS NOT NULL)::int
      + (team_id    IS NOT NULL)::int
      + (service_id IS NOT NULL)::int = 1
    )
);

CREATE INDEX sources_org_idx     ON sources(org_id);
CREATE INDEX sources_team_idx    ON sources(team_id);
CREATE INDEX sources_service_idx ON sources(service_id);
```

### Modified tables

```sql
ALTER TABLE kg_documents
    ADD COLUMN source_id  UUID REFERENCES sources(id) ON DELETE CASCADE,
    ADD COLUMN org_id     UUID REFERENCES organizations(id),
    ADD COLUMN team_id    UUID REFERENCES teams(id),
    ADD COLUMN service_id UUID REFERENCES services(id);

CREATE INDEX kg_documents_org_idx     ON kg_documents(org_id);
CREATE INDEX kg_documents_team_idx    ON kg_documents(team_id);
CREATE INDEX kg_documents_service_idx ON kg_documents(service_id);
```

OpenSearch chunks also need `org_id`, `team_id`, `service_id` fields added to the index mapping for filter pushdown at search time.

### Dropped (replaced by `teams`/`services`)

| Old table | Why removed |
|---|---|
| `kg_teams` | Inferred catalog → replaced by declared `teams` |
| `kg_services` | Inferred catalog → replaced by declared `services` |
| `kg_ownership` | Implicit now (`services.team_id`) |

`kg_dependencies` stays — service-to-service edges remain cross-team and are still extracted from docs. We change its columns from `(from_service TEXT, to_service TEXT)` to `(from_service_id UUID, to_service_id UUID)`. Dependencies whose target service hasn't been declared yet stay as a string in a sidecar table (`kg_pending_dependencies`) and get reconciled when the missing service appears.

## Phasing

### Phase 1 — MVP: one org, GitLab only, hard-coded auth

Goal: prove end-to-end. A user can create an org, a team, a service, attach a GitLab project as a source, ingest it, and see chunks tagged with the right scope. No multi-tenant, no RBAC, no scheduled sync.

**Deliverables**

| Area | Deliverable |
|---|---|
| Schema | New tables migrated; `kg_documents` columns added; old `kg_teams`/`kg_services`/`kg_ownership` dropped; `kg_dependencies` migrated |
| Backend module | `backend/src/catalog/` with `org_repo.py`, `team_repo.py`, `service_repo.py`, `source_repo.py` |
| API | `POST/GET/PATCH/DELETE /api/orgs`, `…/orgs/{id}/teams`, `…/teams/{id}/services`, `…/sources`, `POST /api/sources/{id}/ingest` |
| GitLab connector | `backend/src/connectors/gitlab.py` rewritten: takes `SourceConfig` (base URL, group/project path, PAT), lists projects, fetches READMEs + markdown docs + CODEOWNERS |
| Pipeline | `IngestionPipeline.ingest_source(source_id)` replaces `ingest_all(data_dir)`. Every doc tagged with the source's scope. |
| OpenSearch | Index mapping updated (`org_id`, `team_id`, `service_id`); reindex required |
| UI | New `/setup` flow: create org → add team → add service → add source. Source page shows ingest status + "Sync now". Existing `/sources` page lists declared sources, not the four hard-coded platforms. |
| Cleanup | Delete `data/sources/*` and `scripts/seed_data.py`. Remove the seed step from `run.sh`. |

**Open questions to resolve before starting Phase 1** — see [Open Questions](#open-questions) below.

### Phase 2 — Polish

| Area | Deliverable |
|---|---|
| UI | Replace dashboard "Teams" widget with the declared list; team detail page shows owned services + sources |
| Connectors | SharePoint and Excel connectors take `SourceConfig` too (parity with GitLab) |
| Source health | Per-source status badges, last-sync timestamp, error surfacing |
| Search filters | Search UI exposes scope filters (org/team/service) backed by the new chunk fields |
| Retrieval | `HybridSearchEngine.search(..., scope_filter=...)` accepts `(org_id, team_ids, service_ids)` and pushes down to OpenSearch |

### Phase 3 — Operate

| Area | Deliverable |
|---|---|
| Multi-org | Org picker in UI; per-org isolation in retrieval |
| RBAC | User accounts; per-team membership; sources only editable by team members |
| Scheduled sync | Cron-style re-ingest per source with backoff |
| Source-level filters | Per-source allow/deny path patterns inside a GitLab project |
| Secret store | Tokens move out of the DB into a real secret backend |

## Retrieval Behavior

For an analysis routed to **Team X working on Service Y in Org Z**, the chunk filter becomes:

```sql
WHERE org_id = Z
  AND (team_id    IS NULL OR team_id    = X)
  AND (service_id IS NULL OR service_id = Y)
```

Org-scoped chunks always match. Team-scoped chunks match only when their team is in scope. Service-scoped chunks match only their own service. This pushes down to OpenSearch as filter clauses on the indexed fields — no scoring impact, big precision impact.

The router agent picks the team(s) before this filter is applied. Two-stage:
1. **Routing pass** — search across the full org with no team/service filter; rank by relevance to identify candidate teams/services.
2. **Deep-dive pass** — re-search with `(team_id, service_id)` constraints from the routing pass, plus org-wide context.

## GitLab Connector

**Auth** — personal access token with `read_api` + `read_repository`. Stored in `sources.secret_ref` pointing to a row in a `source_secrets` table (encrypted at rest later; plaintext in DB for Phase 1). `PRISM_GITLAB_BASE_URL` env var defaults to `https://gitlab.com/api/v4` and can be overridden for self-hosted.

**Source config shape** (one of):

```jsonc
// Whole group (recursively pulls all projects, including subgroups)
{ "kind": "gitlab", "group_path": "platform-team", "include_subgroups": true }

// Single project
{ "kind": "gitlab", "project_path": "platform-team/api-gateway", "ref": "main" }
```

**What gets fetched per project**

- `README.md`, `README.rst`, `README.txt`
- Anything under `docs/`, `runbooks/`, `architecture/` (configurable later)
- `CODEOWNERS` (parsed for team→path hints; not used for primary ownership in Phase 1)
- `.gitlab-ci.yml` (skipped — not knowledge content)
- Project metadata: name, description, topics, default branch, web URL

**Per-document scope** — every fetched doc gets the scope of its source (org / team / service). Project metadata becomes the document's title; web URL becomes its `source_url`.

## API Surface (Phase 1)

```
POST   /api/orgs                              { name }
GET    /api/orgs
GET    /api/orgs/{id}
PATCH  /api/orgs/{id}                         { name? }
DELETE /api/orgs/{id}

POST   /api/orgs/{id}/teams                   { name, description? }
GET    /api/orgs/{id}/teams
GET    /api/teams/{id}
PATCH  /api/teams/{id}                        { name?, description? }
DELETE /api/teams/{id}

POST   /api/teams/{id}/services               { name, repo_url?, description? }
GET    /api/teams/{id}/services
GET    /api/services/{id}
PATCH  /api/services/{id}
DELETE /api/services/{id}

POST   /api/sources                           { scope: 'org'|'team'|'service', scope_id, kind, name, config, token? }
GET    /api/sources?org_id=&team_id=&service_id=
GET    /api/sources/{id}
PATCH  /api/sources/{id}
DELETE /api/sources/{id}
POST   /api/sources/{id}/ingest               -> 202 + job id
GET    /api/sources/{id}/status
```

The existing `/api/graph/*` routes (teams, conflicts, dependencies) stay but now read from `teams`/`services`/`kg_dependencies`. The `kg_ownership` conflict endpoint disappears (under the declared model, conflicts can't happen at the data layer).

## UI Flow (Phase 1)

```
/setup                  empty-state wizard if no org exists
  → "Create your organization" form

/orgs/{id}              org detail
  → list of teams
  → "Org-level sources" section
  → "Add team" button

/teams/{id}             team detail
  → list of services
  → "Team-level sources" section
  → "Add service" button

/services/{id}          service detail
  → "Service-level sources" section
  → recent docs ingested

/sources/new            wizard
  → step 1: pick scope (org / team / service) and which one
  → step 2: pick connector kind (gitlab for now)
  → step 3: kind-specific config form (paste PAT, group/project path)
  → step 4: validate (test connection) + save + ingest
```

Replaces today's hard-coded `/sources` page that shows the four seed platforms.

## Cleanup Tasks

| Task | Notes |
|---|---|
| Delete `data/sources/excel`, `data/sources/gitlab`, `data/sources/onenote`, `data/sources/sharepoint` | All seed data |
| Delete `scripts/seed_data.py` | Generator no longer needed |
| Remove seed-data step from `run.sh` | The "186 documents generated across 4 platforms" path |
| Truncate `kg_documents`, `kg_dependencies`, `document_registry` | Existing seed-derived rows |
| Drop `kg_teams`, `kg_services`, `kg_ownership` | Replaced by `teams` / `services` |
| Update `docs/data-flow.md`, `docs/architecture.md` | Reflect declared ownership model |
| Update `README.md` | Quickstart no longer "just run ./run.sh" — needs a setup step |

## Open Questions

These need answers before Phase 1 starts. They each materially affect the schema or API.

1. **Service identity scope** — globally unique service names, or per-team? Real orgs sometimes have `team-a/auth` and `team-b/auth` as different services. Recommendation: **per-team (composite key)** to avoid forced renames at onboarding. Locks in `services.UNIQUE(team_id, name)` as above.

2. **Multi-tenancy** — is "the org" always implicit (single-tenant app), or do we model it explicitly from day one? Recommendation: **explicit org table from day one**, default to a single auto-created org for Phase 1. Costs nothing now, saves a painful migration later.

3. **Source overlap** — can the same GitLab project be a source for two services in different teams? Recommendation: **no, one source = one scope**. If two teams both need that data, they each create their own source; the underlying connector dedupes by content hash anyway.

4. **Conflict semantics** — under the declared model, a service has exactly one team. `kg_ownership` conflicts can't exist. Want to keep the conflict-reporting UI surface for something else (e.g. "two declared sources point at the same GitLab project")? Recommendation: **drop the conflict surface entirely in Phase 1**, revisit if a real conflict shape emerges.

5. **Cross-team service references in deps** — when a doc says "depends on `auth-service`" but no service of that name has been declared yet, do we (a) drop the dep, (b) store it as a pending string, or (c) auto-create a stub service? Recommendation: **(b) pending sidecar table**, reconciled when a matching service appears. Avoids data loss without polluting the declared catalog.

6. **GitLab auth storage for Phase 1** — plaintext PAT in `sources.config`/`source_secrets`, env-var reference, or wait for a real secret store? Recommendation: **plaintext in DB for Phase 1, marked as TODO**. Replace in Phase 3.

7. **Backwards compat during the transition** — keep `/api/ingest` (the legacy ingest-by-data-dir endpoint) working alongside `/api/sources/{id}/ingest`, or break it? Recommendation: **break it cleanly**. This is a POC; transitional shims add code without users.

## Out of Scope (this iteration)

To keep the diff bounded, explicitly **not** doing in Phase 1:

- User accounts, login, RBAC
- Multiple connectors per source
- Webhook-driven sync (push from GitLab on commit)
- Source-level path filters (only ingest `docs/**`)
- Conflict detection at any layer
- A migration path for existing seed-data deployments — the old data gets wiped
- Backwards-compatible `/api/graph/*` payloads — shape will change to include scope IDs

## Definition of Done — Phase 1

- A fresh user can run `./run.sh`, land on the UI, complete the setup wizard with their own GitLab token, and see a populated knowledge base scoped to a real team/service.
- An analysis run produces a brief that cites only docs from in-scope teams/services + org-wide context.
- All 45 existing tests still pass; new tests cover the catalog repos and the GitLab connector's source-config path.
- No references to `data/sources/*` or `seed_data.py` remain.
