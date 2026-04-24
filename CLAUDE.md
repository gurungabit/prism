# CLAUDE.md — Working notes for AI agents on this repo

This file is read on every session. Keep it short and operational.

## What PRISM is

PRISM is a multi-agent platform that ingests org documentation (GitLab
projects, wikis, etc.) into a scope-aware vector store and runs
LangGraph-driven analyses over it. Surfaces: **Analyze** (long
multi-agent runs that produce a `PRISMReport`), **Search** (scope-filtered
hybrid retrieval), **Chat** (grounded follow-ups), and a **Setup /
Sources / Organization** UI on top of the declared catalog (orgs →
teams → services → sources).

Backend is FastAPI + asyncio + Postgres + OpenSearch + Redis. Frontend
is React + Vite + TanStack Router/Query, deployed via `./run.sh`.

Read [`docs/README.md`](docs/README.md) before changing anything
non-trivial. The map of "where things live" is there.

## Repo layout (brief)

```text
backend/src/        # FastAPI app + agents + ingestion + retrieval
ui/src/             # Vite + React app
docs/               # Internal design docs (architecture, agents, data-flow, …)
docker-compose.yml  # OpenSearch + Postgres + Redis for local dev
run.sh              # one-shot dev runner; --clean wipes volumes
```

## Required habits when changing code

1. **Update the docs in the same commit** when you change behavior the
   docs cover. The mapping of doc → topic is in
   [`docs/README.md`](docs/README.md). If you add a new feature with no
   matching doc, add a section to the closest one (or a new file with a
   link from `docs/README.md`).
2. **Read before you write.** The `Explore` agent is fast for
   "where does X live" — use it instead of guessing. Specifically check
   for existing shared components before creating a parallel copy
   (e.g. `components/catalog/{Org,Team,Service}Form.tsx`,
   `components/sources/GitlabEntitySelect.tsx`).
3. **Verify in the running preview** when the change is observable.
   Backend on `:8000`, UI on `:5173`. Don't claim a UI fix is done from
   diff inspection alone.
4. **Don't create test entities silently.** If you need an org / team /
   service / source to verify a feature, ask first or clean up after
   yourself (the user has called this out before).

## Hot spots to be careful around

- **Service dependencies are user-managed.** No LLM/regex extraction
  (we removed `entity_extractor.py` + `kg_pending_dependencies` in
  commit `bf4f680`). Edges are written by the
  `DependenciesSection` UI on the service detail page through
  `POST/DELETE /api/services/{id}/dependencies`.
- **GitLab token lives server-side** (`PRISM_GITLAB_TOKEN`). The wizard
  doesn't collect a per-source token. The project + group dropdowns hit
  `/api/gitlab/{projects,groups}/search`.
- **Group ingest filters dormant projects** via `last_activity_after`
  (`PRISM_GITLAB_GROUP_ACTIVE_WINDOW_DAYS`, default 30). Per-project
  doc count is uncapped — pull every `.md` / `.markdown` / `.rst`.
- **Threads** carry an LLM-generated `title`, a `thread_transcript`
  state field that every downstream prompt injects, and an
  `effective_requirement` rewrite for "rerun" follow-ups. See
  [`docs/threading.md`](docs/threading.md).
- **Schema changes** without `ALTER TABLE` self-healing migrations
  require `./run.sh --clean` to wipe volumes. Document the wipe in the
  commit message if you're going that route.
- **Orphaned `syncing` sources** auto-recover on backend startup
  (`reset_orphaned_syncing` in `main.py` lifespan). Don't try to fix
  this from the UI side.

## Style notes

- Comments explain *why*, not *what*. Restating the code's literal
  effect in prose is dead weight.
- Keep PR/commit messages tight and behavior-focused — no marketing,
  no bullet-point explosions. The repo's existing log is the style guide.
- Don't add emojis to source files unless explicitly asked.

## Pointers for AI contributors

- `AGENTS.md` is the entry point for agent-first contributors. It just
  points back here and to `docs/README.md`.
- The development loop, env vars, and tuning knobs live in
  [`docs/development.md`](docs/development.md) and
  [`docs/deployment.md`](docs/deployment.md).
