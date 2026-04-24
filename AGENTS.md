# AGENTS.md

Entry point for AI agents (Claude Code, Cursor, OpenAI Codex CLI,
Aider, etc.) contributing to this repo.

## Read this first

All operational notes — repo shape, hot spots, required habits, the
"update docs in the same commit" rule — live in
[`CLAUDE.md`](CLAUDE.md). This file just points there so agents that
look for `AGENTS.md` by convention land in the right place.

If you're an AI agent: **load `CLAUDE.md` and `docs/README.md` before
making non-trivial changes**. The docs index in `docs/README.md` tells
you which doc owns which subsystem so you can scan the right one.

## Quick map

| Where | What's there |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Working rules, hot spots, style notes |
| [`docs/README.md`](docs/README.md) | Doc index — every internal-design doc and what it covers |
| [`docs/architecture.md`](docs/architecture.md) | System topology + declared ownership model |
| [`docs/agents.md`](docs/agents.md) | LangGraph orchestrator + per-agent responsibilities |
| [`docs/data-flow.md`](docs/data-flow.md) | Ingestion + retrieval pipelines |
| [`docs/threading.md`](docs/threading.md) | Multi-turn analysis: titles, transcripts, reruns |
| [`docs/api.md`](docs/api.md) | REST + SSE endpoint reference |
| [`docs/deployment.md`](docs/deployment.md) | Local stack, env vars, ops |
| [`docs/development.md`](docs/development.md) | Project layout + extension points |

## House rules (short version)

- Update the docs in the same commit when you change behavior the docs
  cover. See [`CLAUDE.md`](CLAUDE.md) for the full list.
- Reuse existing shared components before creating new ones — see
  `ui/src/components/catalog/` and `ui/src/components/sources/` first.
- Don't seed data silently to verify features; ask first or clean up
  after yourself.
- Verify UI changes in the running preview, not just from the diff.
