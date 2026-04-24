# PRISM Documentation

This folder is the source of truth for how PRISM works. The top-level
`README.md` is the user-facing pitch + quickstart; everything here is
internal-design material aimed at people writing or reviewing code.

## How to use

- Skim `architecture.md` first to understand the shape of the system
  (orgs → teams → services → sources → chunks → agents).
- Then dive into the area you're touching — `data-flow.md` for
  ingestion + retrieval, `agents.md` for the orchestrator, `api.md` for
  HTTP endpoints, `threading.md` for multi-turn analyses.
- `deployment.md` and `development.md` are operator/contributor guides.

## Index

| Doc | Owns |
|---|---|
| [architecture.md](architecture.md) | System topology, declared ownership model, catalog schema, ingestion + analysis sequence diagrams, deployment view |
| [data-flow.md](data-flow.md) | Ingestion pipeline (connectors → parse → chunk → scope-tag → embed → index), GitLab connector specifics (wiki, group active filter, vendor skiplist), incremental ingestion, retrieval pipeline, scope-filter semantics, manual service dependencies |
| [agents.md](agents.md) | LangGraph orchestrator, planner (mode + agents + thread transcript + rerun rewrite + title generation), per-agent responsibilities, shared state, graceful degradation |
| [threading.md](threading.md) | Multi-turn analyses: titles, prior-turn transcripts, rerun handling, schema |
| [api.md](api.md) | REST + SSE endpoint reference: analysis, search, chat, catalog CRUD, sources, manual deps, threads, GitLab autocomplete, report shape |
| [deployment.md](deployment.md) | Local Docker stack, ports, env vars (incl. `PRISM_GITLAB_TOKEN`, `PRISM_GITLAB_GROUP_ACTIVE_WINDOW_DAYS`), `./run.sh --clean`, orphaned-source recovery, AWS migration paths |
| [development.md](development.md) | Prerequisites, project layout, testing, extension points (connectors, agents, report export), tuning knobs, docs hygiene |

## Updating the docs

When you change behavior the docs cover, **update the docs in the same
commit**. Reviewers will push back on undocumented behavior changes.
The rules and a quick checklist live in [`/CLAUDE.md`](../CLAUDE.md);
[`/AGENTS.md`](../AGENTS.md) points contributing AI agents at the same
material.
