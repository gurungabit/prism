from __future__ import annotations

import json
import time
import uuid
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agents.orchestrator import run_analysis
from src.api.chat import _conversations, chat_stream
from src.api.streaming import create_step_callback, event_store, stream_events
from src.catalog import ServiceRepository, TeamRepository
from src.config import settings
from src.ingestion.analysis_store import AnalysisRepository
from src.ingestion.indexer import get_opensearch_client
from src.models.report import AnalysisInput
from src.observability.logging import get_logger
from src.retrieval.hybrid_search import HybridSearchEngine
from src.retrieval.knowledge_queries import (
    get_all_teams,
    get_service_dependencies,
    get_service_ownership,
    get_team_profile,
)

log = get_logger("routes")

router = APIRouter(prefix="/api")

_analyses: dict[str, dict] = {}


class AnalyzeRequest(BaseModel):
    requirement: str
    business_goal: str = ""
    context: str = ""
    constraints: str = ""
    known_teams: str = ""
    known_services: str = ""
    questions_to_answer: str = ""
    # Threading: when set, this run is a follow-up in an existing thread.
    # The backend loads the parent's (+ earlier turns') context before
    # kicking off the pipeline.
    parent_analysis_id: str | None = None
    # When true, force full-analysis mode even on follow-ups. Used by the UI's
    # "Run full analysis" button on chat-mode responses.
    force_full: bool = False

    def to_analysis_input(self) -> AnalysisInput:
        return AnalysisInput(
            requirement=self.requirement,
            business_goal=self.business_goal,
            context=self.context,
            constraints=self.constraints,
            known_teams=self.known_teams,
            known_services=self.known_services,
            questions_to_answer=self.questions_to_answer,
        )


class SearchRequest(BaseModel):
    query: str
    filters: dict = {}
    top_k: int | None = None
    page: int = 1
    page_size: int = 40
    # Declared-scope filter, pushed into OpenSearch. Keys match
    # ``HybridSearchEngine.scope_filter``: org_id, team_ids[], service_ids[].
    scope: dict | None = None


class FeedbackRequest(BaseModel):
    section: str
    correct_answer: str
    reason: str = ""


@router.post("/analyze")
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    analysis_id = str(uuid.uuid4())
    analysis_input = request.to_analysis_input()

    # Thread bookkeeping: if this is a follow-up, inherit the parent's
    # thread_id; otherwise this run starts a new thread (thread_id defaults
    # to analysis_id in the repo).
    thread_id = analysis_id
    parent_row = None
    if request.parent_analysis_id:
        try:
            repo = await AnalysisRepository.create()
            parent_row = await repo.get(request.parent_analysis_id)
            await repo.close()
        except Exception as db_err:
            log.warning(
                "analysis_parent_lookup_failed",
                parent=request.parent_analysis_id,
                error=str(db_err),
            )
        if parent_row is None:
            raise HTTPException(status_code=404, detail="parent_analysis_id not found")
        thread_id = parent_row.get("thread_id") or parent_row["analysis_id"]

    _analyses[analysis_id] = {
        "status": "running",
        "requirement": request.requirement,
        "analysis_input": analysis_input.model_dump(),
        "report": None,
    }

    try:
        repo = await AnalysisRepository.create()
        await repo.insert(
            analysis_id,
            request.requirement,
            thread_id=thread_id,
            parent_analysis_id=request.parent_analysis_id,
            # We don't know kind yet (the planner decides). Start as 'full'
            # and the task below updates it once the plan resolves. The UI
            # treats in-flight runs as unknown anyway.
            kind="full",
        )
        await repo.close()
    except Exception as db_err:
        log.warning("analysis_db_insert_failed", analysis_id=analysis_id, error=str(db_err))

    background_tasks.add_task(
        _run_analysis_task,
        analysis_id,
        analysis_input.model_dump(),
        thread_id,
        request.parent_analysis_id,
        request.force_full,
    )

    return {
        "analysis_id": analysis_id,
        "thread_id": thread_id,
        "stream_url": f"/api/analyze/{analysis_id}/stream",
    }


async def _load_prior_turns(thread_id: str, parent_analysis_id: str) -> list[dict]:
    """Load every completed turn before ``parent_analysis_id`` plus the
    parent itself, oldest first. The orchestrator's planner + chat node
    consume this list as its thread context.
    """
    try:
        repo = await AnalysisRepository.create()
        try:
            rows = await repo.list_thread(thread_id)
        finally:
            await repo.close()
    except Exception as db_err:
        log.warning("thread_load_failed", thread_id=thread_id, error=str(db_err))
        return []

    out: list[dict] = []
    for row in rows:
        if row["analysis_id"] == parent_analysis_id:
            # include the parent itself, then stop walking forward
            out.append(_turn_from_row(row))
            break
        if row["status"] == "complete":
            out.append(_turn_from_row(row))
    return out


def _turn_from_row(row: dict) -> dict:
    report = row.get("report") or {}
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except json.JSONDecodeError:
            report = {}
    return {
        "analysis_id": row["analysis_id"],
        "requirement": row["requirement"],
        "kind": row.get("kind", "full"),
        "rolling_summary": row.get("rolling_summary", "") or "",
        "report": report if isinstance(report, dict) else {},
        # We intentionally don't persist per-run chunks -- chat-mode merges
        # chunks from prior-turn reports via ``report.all_sources`` if
        # needed. Keeping this field for parity with the state shape.
        "retrieved_chunks": [],
    }


async def _run_analysis_task(
    analysis_id: str,
    analysis_input_data: dict,
    thread_id: str,
    parent_analysis_id: str | None,
    force_full: bool,
) -> None:
    on_step = create_step_callback(analysis_id)
    started_at = time.monotonic()
    analysis_input = AnalysisInput.model_validate(analysis_input_data)

    prior_turns = (
        await _load_prior_turns(thread_id, parent_analysis_id)
        if parent_analysis_id
        else []
    )

    # "Run full analysis" button on a chat response: strip prior_turns so the
    # planner re-enters first-turn mode and can't downgrade to chat.
    if force_full:
        prior_turns = []

    try:
        result = await run_analysis(
            requirement=analysis_input.requirement,
            analysis_id=analysis_id,
            analysis_input=analysis_input,
            on_step=on_step,
            prior_turns=prior_turns,
        )

        duration = time.monotonic() - started_at
        report_dict = result.report.model_dump(mode="json")
        # Embed chat payload on the stored report so the UI can distinguish
        # chat vs full turns without hitting a second endpoint.
        if result.kind == "chat" and result.chat_answer:
            report_dict["chat_answer"] = result.chat_answer
        report_dict["kind"] = result.kind
        report_dict["thread_id"] = thread_id
        report_dict["parent_analysis_id"] = parent_analysis_id

        _analyses[analysis_id]["status"] = "complete"
        _analyses[analysis_id]["report"] = report_dict

        await event_store.publish_complete(analysis_id, report_dict)

        try:
            repo = await AnalysisRepository.create()
            await repo.update_complete(analysis_id, report_dict, duration)
            # Planner may have flipped kind to 'chat'; make sure the DB row
            # reflects the actual run type.
            if result.kind != "full":
                async with repo.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE analyses SET kind = $2 WHERE analysis_id = $1",
                        analysis_id,
                        result.kind,
                    )
            if result.rolling_summary:
                await repo.update_rolling_summary(analysis_id, result.rolling_summary)
            await repo.close()
        except Exception as db_err:
            log.warning(
                "analysis_db_update_complete_failed",
                analysis_id=analysis_id,
                error=str(db_err),
            )

    except Exception as e:
        log.error("analysis_task_failed", analysis_id=analysis_id, error=str(e))
        _analyses[analysis_id]["status"] = "failed"
        _analyses[analysis_id]["error"] = str(e)

        await event_store.publish(
            analysis_id,
            {
                "type": "error",
                "error": str(e),
            },
        )
        await event_store.publish_complete(analysis_id, {"error": str(e)})

        try:
            repo = await AnalysisRepository.create()
            await repo.update_failed(analysis_id, str(e))
            await repo.close()
        except Exception as db_err:
            log.warning("analysis_db_update_failed_failed", analysis_id=analysis_id, error=str(db_err))


@router.get("/analyze/{analysis_id}/stream")
async def stream_analysis(analysis_id: str, request: Request):
    last_event_id = request.headers.get("Last-Event-ID")

    has_events = len(event_store.get_all_events(analysis_id)) > 0
    in_memory = analysis_id in _analyses

    if not has_events and not in_memory:
        try:
            repo = await AnalysisRepository.create()
            row = await repo.get(analysis_id)
            await repo.close()
        except Exception:
            row = None

        if row and row.get("report") and row["status"] in ("complete", "completed"):
            report_data = row["report"] if isinstance(row["report"], dict) else json.loads(row["report"])
            await event_store.publish_complete(analysis_id, report_data)

    async def event_generator():
        async for event_data in stream_events(analysis_id, last_event_id):
            if await request.is_disconnected():
                break
            yield event_data

    return EventSourceResponse(event_generator(), media_type="text/event-stream")


@router.get("/analyze/{analysis_id}/report")
async def get_report(analysis_id: str):
    analysis = _analyses.get(analysis_id)
    if analysis:
        if analysis["status"] == "running":
            return JSONResponse(
                status_code=202,
                content={"status": "running", "message": "Analysis in progress"},
            )
        if analysis["status"] == "failed":
            raise HTTPException(status_code=500, detail=analysis.get("error", "Analysis failed"))
        return analysis["report"]

    try:
        repo = await AnalysisRepository.create()
        row = await repo.get(analysis_id)
        await repo.close()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if row["status"] == "running":
        return JSONResponse(
            status_code=202,
            content={"status": "running", "message": "Analysis in progress"},
        )
    if row["status"] == "failed":
        raise HTTPException(status_code=500, detail=row.get("error", "Analysis failed"))

    if row.get("report"):
        return row["report"]

    raise HTTPException(status_code=404, detail="Report data not available")


@router.get("/analyze/{analysis_id}/trace")
async def get_trace(analysis_id: str):
    events = event_store.get_all_events(analysis_id)
    return {"analysis_id": analysis_id, "trace": events}


@router.get("/analyze/{analysis_id}/sources")
async def get_sources(analysis_id: str):
    analysis = _analyses.get(analysis_id)
    if not analysis or not analysis.get("report"):
        raise HTTPException(status_code=404, detail="Report not available")
    return {"sources": analysis["report"].get("all_sources", [])}


@router.post("/analyze/{analysis_id}/feedback")
async def submit_feedback(analysis_id: str, feedback: FeedbackRequest):
    log.info(
        "feedback_received",
        analysis_id=analysis_id,
        section=feedback.section,
        correction=feedback.correct_answer[:100],
    )
    return {"status": "received", "message": "Feedback recorded for future improvement"}


@router.post("/search")
async def search_documents(request: SearchRequest):
    page = max(request.page, 1)
    page_size = min(max(request.top_k or request.page_size, 1), 100)
    offset = (page - 1) * page_size
    fetch_limit = max(offset + page_size + 1, 200)

    engine = HybridSearchEngine()
    chunks = await engine.search(
        requirement=request.query,
        top_k=fetch_limit,
        filters=request.filters if request.filters else None,
        expand=False,
        scope_filter=request.scope,
    )

    total = len(chunks) if len(chunks) < fetch_limit else None
    if total is not None:
        max_page = max((total + page_size - 1) // page_size, 1)
        page = min(page, max_page)
        offset = (page - 1) * page_size

    page_chunks = chunks[offset:offset + page_size]
    has_more = (
        offset + page_size < total
        if total is not None
        else len(chunks) > offset + page_size
    )

    rrf_k = 60
    num_lists = 2  # 1 BM25 + 1 vector with expand=False
    theoretical_max = num_lists / (rrf_k + 1)

    return {
        "query": request.query,
        "results": [
            {
                "chunk_id": c.chunk_id,
                "content": c.content[:500],
                "score": round(min(c.score / theoretical_max, 1.0), 3),
                "source_path": c.metadata.source_path,
                "document_title": c.metadata.document_title,
                "doc_type": c.metadata.doc_type,
                "platform": c.metadata.source_platform,
                "org_id": str(c.metadata.org_id) if c.metadata.org_id else None,
                "team_id": str(c.metadata.team_id) if c.metadata.team_id else None,
                "service_id": str(c.metadata.service_id) if c.metadata.service_id else None,
            }
            for c in page_chunks
        ],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
        "total": total,
    }


# ---------- graph endpoints (now catalog-backed) ----------


@router.get("/graph/teams")
async def list_teams():
    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    try:
        teams = await get_all_teams(team_repo, service_repo)
    finally:
        await service_repo.close()
        await team_repo.close()
    return {"teams": teams}


@router.get("/graph/teams/{team_name}")
async def get_team(team_name: str):
    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    try:
        profile = await get_team_profile(team_repo, service_repo, team_name)
    finally:
        await service_repo.close()
        await team_repo.close()
    return profile


@router.get("/graph/services/{service_name}")
async def get_service(service_name: str):
    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    try:
        owners = await get_service_ownership(team_repo, service_repo, service_name)
        deps = await get_service_dependencies(service_repo, service_name)
    finally:
        await service_repo.close()
        await team_repo.close()
    return {"service": service_name, "owners": owners, "dependencies": deps}


@router.get("/graph/dependencies/{service_name}")
async def get_dependencies(service_name: str, depth: int = Query(default=2, ge=1, le=5)):
    service_repo = await ServiceRepository.create()
    try:
        deps = await get_service_dependencies(service_repo, service_name, depth)
    finally:
        await service_repo.close()
    return {"service": service_name, "depth": depth, "dependencies": deps}


# ``/api/graph/conflicts`` is removed in Phase 1 (plan open question 4). The
# declared catalog can't produce ownership conflicts at the data layer, so
# the endpoint was returning misleading data. The UI widget is also removed.


@router.delete("/history/{analysis_id}")
async def delete_analysis(analysis_id: str):
    repo = await AnalysisRepository.create()
    deleted = await repo.delete(analysis_id)
    await repo.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found")
    _analyses.pop(analysis_id, None)
    return {"status": "deleted", "analysis_id": analysis_id}


@router.get("/history")
async def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List analysis threads (one row per thread, not per run).

    The UI renders each row as a collapsible thread card showing the root
    requirement, turn count, and last activity. Clicking opens
    ``/analyze/<thread_id>`` which renders the stacked thread view.
    """
    repo = await AnalysisRepository.create()
    threads = await repo.list_threads(limit=limit, offset=offset)
    total = await repo.count_threads()
    await repo.close()
    return {"threads": threads, "total": total}


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Full ordered list of runs in a thread, oldest-first.

    The URL segment accepts either a thread_id or any run_id within the
    thread -- the API resolves down to the thread_id so links from older
    single-run analyses still work.

    Each run carries its requirement, kind ('full' or 'chat'), status,
    rolling_summary, and the stored report (which contains either a full
    PRISMReport or a chat_answer payload).
    """
    repo = await AnalysisRepository.create()
    try:
        rows = await repo.list_thread(thread_id)
        if not rows:
            # Caller passed a run_id that isn't a thread root. Resolve via
            # the run's row and re-query by its real thread_id.
            row = await repo.get(thread_id)
            if row and row.get("thread_id"):
                thread_id = row["thread_id"]
                rows = await repo.list_thread(thread_id)
    finally:
        await repo.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Thread not found")

    turns: list[dict] = []
    for row in rows:
        report = row.get("report")
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except json.JSONDecodeError:
                report = None
        turns.append(
            {
                "analysis_id": row["analysis_id"],
                "parent_analysis_id": row.get("parent_analysis_id"),
                "kind": row.get("kind", "full"),
                "requirement": row["requirement"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "duration_seconds": row.get("duration_seconds"),
                "rolling_summary": row.get("rolling_summary", "") or "",
                "report": report,
            }
        )
    return {"thread_id": thread_id, "turns": turns}


@router.get("/analyze/resolve/{analysis_id}")
async def resolve_analysis_thread(analysis_id: str) -> dict:
    """Cheap ``run_id -> thread_id`` lookup. The UI uses this to redirect
    ``/analyze/<runId>`` URLs to the canonical ``/analyze/<threadId>`` URL
    when the runId isn't already the thread root.
    """
    repo = await AnalysisRepository.create()
    try:
        row = await repo.get(analysis_id)
    finally:
        await repo.close()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {
        "analysis_id": analysis_id,
        "thread_id": row.get("thread_id") or analysis_id,
    }


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@router.post("/chat")
async def chat(request_body: ChatRequest, request: Request):
    async def event_generator():
        async for event_data in chat_stream(request_body.message, request_body.conversation_id):
            if await request.is_disconnected():
                break
            yield event_data

    return EventSourceResponse(event_generator(), media_type="text/event-stream")


@router.get("/chat/conversations")
async def list_conversations():
    convos = []
    for conv_id, messages in _conversations.items():
        if messages:
            convos.append(
                {
                    "conversation_id": conv_id,
                    "message_count": len(messages),
                    "last_message": messages[-1]["content"][:100] if messages else "",
                    "preview": messages[0]["content"][:100] if messages else "",
                }
            )
    return {"conversations": convos}


@router.get("/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    messages = _conversations.get(conversation_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "messages": messages}


@router.get("/chat/source-preview/by-path")
async def get_chat_source_preview(
    source_path: str = Query(...),
    source_platform: str | None = Query(default=None),
):
    client = get_opensearch_client()
    body: dict = {
        "size": 1,
        "sort": [{"chunk_index": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"source_path": source_path}},
                ]
            }
        },
    }

    if source_platform:
        body["query"]["bool"]["filter"].append({"term": {"source_platform": source_platform}})

    try:
        response = client.search(
            index=settings.opensearch_index,
            body=body,
            params={"search_pipeline": "_none"},
        )
        hits = response.get("hits", {}).get("hits", [])

        if hits and not hits[0].get("_source", {}).get("content", "").strip():
            body_with_content = {
                "size": 1,
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"source_path": source_path}},
                            {"exists": {"field": "content"}},
                        ],
                        "must": [
                            {"match_all": {}},
                        ],
                    }
                },
            }
            if source_platform:
                body_with_content["query"]["bool"]["filter"].append(
                    {"term": {"source_platform": source_platform}}
                )
            retry = client.search(
                index=settings.opensearch_index,
                body=body_with_content,
                params={"search_pipeline": "_none"},
            )
            retry_hits = retry.get("hits", {}).get("hits", [])
            if retry_hits and retry_hits[0].get("_source", {}).get("content", "").strip():
                hits = retry_hits

        if not hits:
            raise HTTPException(status_code=404, detail="Source preview not found")

        source = hits[0].get("_source", {})
        return {
            "source_path": source.get("source_path", source_path),
            "source_platform": source.get("source_platform", source_platform or ""),
            "title": source.get("document_title", ""),
            "section_heading": source.get("section_heading", ""),
            "content": source.get("content", ""),
            "score": hits[0].get("_score", 0.0),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("chat_source_preview_failed", source_path=source_path, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load source preview") from e


@router.delete("/chat/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if conversation_id in _conversations:
        del _conversations[conversation_id]
        return {"status": "deleted", "conversation_id": conversation_id}
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "prism-api"}
