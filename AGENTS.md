# AGENTS.md

The entry point for AI agents (and humans) working on this repo.

## What PRISM is, in one paragraph

A multi-agent platform that ingests org documentation (GitLab projects,
wikis, etc.) into a scope-aware vector store and runs LangGraph-driven
analyses over it. Surfaces: **Analyze** (long multi-agent runs that
produce a `PRISMReport`), **Search** (scope-filtered hybrid retrieval),
**Chat** (grounded follow-ups), and a **Setup / Sources / Organization**
UI on top of the declared catalog (orgs → teams → services → sources).
FastAPI + Postgres + OpenSearch + Redis on the backend; React + Vite +
TanStack on the frontend.

The map of "where things live" is in [`docs/README.md`](docs/README.md).
Read it before changing anything non-trivial.

## How to behave

These are the patterns I've watched go wrong on this repo. They bias
toward caution; for trivial edits, use judgment.

### Think before coding

Don't assume, don't hide confusion. If you're not sure what the user
means, ask — don't pick an interpretation silently. If a simpler
approach exists, name it; you're allowed to push back. If the request
is ambiguous, list the options and let the user pick.

### Stay surgical

Every changed line should trace directly to what was asked. Don't
"improve" adjacent code, reformat unrelated blocks, or refactor things
that aren't broken. Match the existing style even if you'd do it
differently. Clean up imports / variables / functions that **your**
edit orphaned, but don't delete pre-existing dead code unless asked.

### Reuse before you build

This repo already has shared form components, shared GitLab pickers,
shared button / input primitives. Look there first:

- `ui/src/components/catalog/` — `OrgForm`, `TeamForm`, `ServiceForm`,
  `DependenciesSection`. Used by both the wizard and the detail pages.
- `ui/src/components/sources/` — `GitlabEntitySelect` is the shared
  searchable dropdown; `GitlabProjectSelect` and `GitlabGroupSelect`
  are 30-line wrappers over it.
- `ui/src/components/shared/` — `Button`, `Input`, `Textarea`,
  `Modal`, `ConfirmDialog`, `Badge`, `EmptyState`.
- Backend repos in `backend/src/catalog/` already have CRUD methods;
  add API endpoints, don't duplicate the SQL.

If you find yourself writing a 200-line component that already exists
as a 30-line wrapper, stop and re-check.

### Verify, don't guess

UI changes go through the running preview (Vite on `:5173`, API on
`:8000`). Inspect the live DOM or take a screenshot — diff inspection
alone is not verification. Backend changes can be smoke-tested with
`uv run python -c "..."` import checks and `curl` against the running
process.

### Don't seed test data silently

If you need an org / team / service / source to verify a feature, ask
first or clean up after yourself. The user has called this out before.

### Update docs in the same commit

When you change behavior the docs cover, update the matching doc.
[`docs/README.md`](docs/README.md) lists every internal-design doc and
which subsystem it owns. If you ship a feature with no matching doc,
add a section to the closest one.

## Hot spots specific to PRISM

Things easy to get wrong if you don't know the recent history:

- **Service dependencies are user-managed.** No LLM/regex extraction.
  The `entity_extractor.py` module and `kg_pending_dependencies` table
  were removed in `bf4f680`. Edges go through
  `POST/DELETE /api/services/{id}/dependencies`, written by the
  `DependenciesSection` UI on the service detail page.
- **GitLab token lives server-side** (`PRISM_GITLAB_TOKEN`). The wizard
  doesn't collect a per-source token. Dropdowns hit
  `/api/gitlab/{projects,groups}/search`.
- **Group ingest filters dormant projects** via `last_activity_after`
  (`PRISM_GITLAB_GROUP_ACTIVE_WINDOW_DAYS`, default 30). Per-project
  doc count is uncapped — pull every `.md` / `.markdown` / `.rst`.
- **Threads** carry an LLM-generated `title`, a `thread_transcript`
  state field that every downstream prompt injects, and an
  `effective_requirement` rewrite for "rerun" follow-ups. See
  [`docs/threading.md`](docs/threading.md) for the deep dive.
- **Schema changes without `ALTER TABLE` self-healing migrations**
  require `./run.sh --clean` to wipe Docker volumes. Document the wipe
  in the commit message if you go that route.
- **Orphaned `syncing` sources auto-recover** on backend startup
  (`reset_orphaned_syncing` in `main.py` lifespan). Don't try to
  paper over it from the UI.

## Doc map

Skim the doc that owns the area you're touching:

| Doc | Owns |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System topology, declared ownership, catalog schema |
| [`docs/data-flow.md`](docs/data-flow.md) | Ingestion + retrieval; GitLab connector specifics |
| [`docs/agents.md`](docs/agents.md) | LangGraph orchestrator + per-agent details |
| [`docs/threading.md`](docs/threading.md) | Multi-turn analyses (titles, transcripts, reruns) |
| [`docs/api.md`](docs/api.md) | REST + SSE endpoint reference |
| [`docs/deployment.md`](docs/deployment.md) | Local stack, env vars, ops |
| [`docs/development.md`](docs/development.md) | Project layout + extension points |

## Style

- Comments explain *why*, not *what*. Restating the code's literal
  effect in prose is dead weight.
- Commit messages tight, behavior-focused. The repo's existing log is
  the style guide.
- No emojis in source files unless explicitly asked.
- **No `any` in TypeScript** unless genuinely unavoidable (e.g. a
  third-party library typed as `any` upstream). Prefer `unknown` +
  narrowing, generics, or a precise interface. If you truly need `any`,
  leave a one-line comment justifying it. The current codebase has
  effectively zero `any` — keep it that way.
