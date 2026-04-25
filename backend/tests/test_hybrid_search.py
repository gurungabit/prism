import asyncio

from uuid import UUID

import pytest

from src.retrieval.hybrid_search import (
    HybridSearchEngine,
    RetrievalUnavailable,
    _build_scope_clauses,
    _validate_scope_against_lookups,
)


def test_build_filters_supports_scalar_values():
    engine = HybridSearchEngine(client=object())

    clauses = engine._build_filters({"doc_type": "readme", "source_platform": "gitlab"})

    assert {"term": {"source_platform": "gitlab"}} in clauses
    assert {"term": {"doc_type": "readme"}} in clauses


def test_build_filters_supports_multi_select_values():
    engine = HybridSearchEngine(client=object())

    clauses = engine._build_filters(
        {
            "doc_type": ["readme", "wiki"],
            "team_hint": ["payments team"],
            "service_hint": [],
        },
    )

    assert {"terms": {"doc_type": ["readme", "wiki"]}} in clauses
    assert {"terms": {"team_hint": ["payments team"]}} in clauses
    # Empty list should not produce a clause.
    assert not any(
        isinstance(clause, dict) and list(clause.values())[0].get("service_hint") for clause in clauses
    )


def test_scope_filter_builds_nullable_clauses():
    org_id = UUID("11111111-1111-1111-1111-111111111111")
    team_a = UUID("22222222-2222-2222-2222-222222222222")
    team_b = UUID("33333333-3333-3333-3333-333333333333")
    service_a = UUID("44444444-4444-4444-4444-444444444444")

    clauses = _build_scope_clauses(
        {
            "org_id": org_id,
            "team_ids": [team_a, team_b],
            "service_ids": [service_a],
        }
    )

    # org_id is a hard filter (chunks not in the org are never returned).
    assert any(c == {"term": {"org_id": str(org_id)}} for c in clauses)

    # team_id clause: NULL OR team IN (...)
    team_clause = next(c for c in clauses if "bool" in c and any(
        "terms" in child and "team_id" in child.get("terms", {})
        for child in c["bool"].get("should", [])
    ))
    should = team_clause["bool"]["should"]
    assert {"bool": {"must_not": {"exists": {"field": "team_id"}}}} in should
    assert {"terms": {"team_id": [str(team_a), str(team_b)]}} in should

    # service_id clause, same shape.
    service_clause = next(c for c in clauses if "bool" in c and any(
        "terms" in child and "service_id" in child.get("terms", {})
        for child in c["bool"].get("should", [])
    ))
    should = service_clause["bool"]["should"]
    assert {"bool": {"must_not": {"exists": {"field": "service_id"}}}} in should
    assert {"terms": {"service_id": [str(service_a)]}} in should


def test_scope_filter_empty_returns_no_clauses():
    assert _build_scope_clauses({}) == []
    assert _build_scope_clauses({"team_ids": [], "service_ids": None}) == []


# ----- _validate_scope_against_lookups: cross-org guard -----
#
# These tests exercise the pure validation step in isolation -- the DB
# lookup is faked via in-memory dicts so the test runs without Postgres.
# Each one targets a specific leak shape codex flagged in round 4:
# scope IDs that resolve cleanly (the row exists somewhere in the
# catalog) but belong to a *different* org than the one the caller
# pinned.

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
TEAM_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TEAM_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SVC_A = "11aaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SVC_B = "22bbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_validate_scope_drops_cross_org_service_id():
    """Stale bookmark: caller asks for org A but service belongs to org B.

    Before the round-4 fix, the service resolved cleanly so we added
    its parent team (team_B) to ``team_ids`` and kept the service in
    the list. The OpenSearch clauses then admitted org A's org-scoped
    chunks via the ``IS NULL`` branches even though no real chunk
    matched team_B/SVC_B under org A. The expected behavior is
    match-nothing because the caller's narrowing has zero in-org hits.
    """
    result = _validate_scope_against_lookups(
        {"org_id": ORG_A, "service_ids": [SVC_B]},
        service_lookups={SVC_B: (TEAM_B, ORG_B)},
        team_lookups={},
    )
    assert result.get("__match_nothing__") is True


def test_validate_scope_drops_cross_org_team_id():
    """Same shape on the team axis: a team belonging to a different
    org should not widen the requested org's scope."""
    result = _validate_scope_against_lookups(
        {"org_id": ORG_A, "team_ids": [TEAM_B]},
        service_lookups={},
        team_lookups={TEAM_B: ORG_B},
    )
    assert result.get("__match_nothing__") is True


def test_validate_scope_keeps_in_org_targets_and_drops_cross_org_only():
    """Mixed selection: the in-org targets survive; the cross-org ones
    are quietly dropped. The team_ids list ends up as the union of the
    surviving explicit teams + the parent teams of the surviving
    services, which is the same shape ``_expand_scope_with_service_parents``
    would have produced under the legacy code for an in-org-only
    request."""
    result = _validate_scope_against_lookups(
        {
            "org_id": ORG_A,
            "service_ids": [SVC_A, SVC_B],  # SVC_B is cross-org
            "team_ids": [TEAM_A, TEAM_B],   # TEAM_B is cross-org
        },
        service_lookups={
            SVC_A: (TEAM_A, ORG_A),
            SVC_B: (TEAM_B, ORG_B),
        },
        team_lookups={
            TEAM_A: ORG_A,
            TEAM_B: ORG_B,
        },
    )
    assert "__match_nothing__" not in result
    assert result["service_ids"] == [SVC_A]
    assert result["team_ids"] == sorted({TEAM_A})


def test_validate_scope_no_org_id_skips_cross_org_check():
    """Without an explicit ``org_id`` the caller is in legacy un-scoped
    mode -- there's no "wrong org" to drop against. IDs still need to
    resolve, but otherwise pass through."""
    result = _validate_scope_against_lookups(
        {"service_ids": [SVC_A, SVC_B]},
        service_lookups={
            SVC_A: (TEAM_A, ORG_A),
            SVC_B: (TEAM_B, ORG_B),
        },
        team_lookups={},
    )
    assert "__match_nothing__" not in result
    assert sorted(result["service_ids"]) == sorted([SVC_A, SVC_B])


def test_unresolved_service_id_emits_match_nothing_clause():
    """Regression: a stale ``service_id`` (deleted service, bookmark from
    another org) used to leak into the OpenSearch clause as
    ``service_id IS NULL OR service_id IN [unknown-uuid]``. The IS NULL
    branch then admitted every team-scoped chunk in the broader scope.

    The fix sets a ``__match_nothing__`` sentinel on the post-derivation
    filter when none of the requested service IDs resolve, and the clause
    builder turns that into a ``must_not match_all`` so retrieval returns
    zero hits instead of broadening.

    This test exercises the clause shape only; the parent-team derivation
    is async and lives behind ``_expand_scope_with_service_parents``.
    """
    org_id = UUID("11111111-1111-1111-1111-111111111111")

    clauses = _build_scope_clauses({"org_id": org_id, "__match_nothing__": True})
    assert clauses == [{"bool": {"must_not": {"match_all": {}}}}]

    # Sentinel wins over org_id / team / service clauses -- anything else
    # would be a leak, since the scope-resolver has explicitly said
    # "nothing the caller asked for exists".
    sentinel_only = _build_scope_clauses(
        {
            "org_id": org_id,
            "team_ids": [UUID("22222222-2222-2222-2222-222222222222")],
            "service_ids": [UUID("33333333-3333-3333-3333-333333333333")],
            "__match_nothing__": True,
        }
    )
    assert sentinel_only == [{"bool": {"must_not": {"match_all": {}}}}]


def test_service_only_scope_does_not_admit_other_team_docs():
    """Regression: picking ``service_ids=[X]`` without ``team_ids`` used to
    admit team-scoped chunks for *other* teams in the same org via the
    nullable-OR branch. After the fix the team clause is pinned to the
    selected services' parent teams so foreign-team team-scoped chunks
    can't slip through.

    This test exercises the clause shape only -- the parent-team
    derivation is async (requires Postgres) and is covered by an
    integration test elsewhere. Here we hand-build the post-derivation
    scope and assert the resulting clauses are what OpenSearch would
    enforce.
    """
    org_id = UUID("11111111-1111-1111-1111-111111111111")
    parent_team = UUID("22222222-2222-2222-2222-222222222222")
    service_a = UUID("44444444-4444-4444-4444-444444444444")

    # Post-derivation: caller picked only service_a; parent_team was added
    # by ``_expand_scope_with_service_parents`` before we got here.
    clauses = _build_scope_clauses(
        {
            "org_id": org_id,
            "team_ids": [parent_team],
            "service_ids": [service_a],
        }
    )

    team_clause = next(c for c in clauses if "bool" in c and any(
        "terms" in child and "team_id" in child.get("terms", {})
        for child in c["bool"].get("should", [])
    ))
    should = team_clause["bool"]["should"]
    # Only the parent team is allowed; sibling-team chunks are rejected.
    assert {"terms": {"team_id": [str(parent_team)]}} in should
    # The IS NULL branch is still present so org-scoped chunks still match.
    assert {"bool": {"must_not": {"exists": {"field": "team_id"}}}} in should


# ----- RetrievalUnavailable propagation -----


class _FakeFailingClient:
    """Minimal stand-in for the OpenSearch client that always errors.

    ``HybridSearchEngine`` accepts an injected client, so we can
    exercise the all-calls-failed path without a live OpenSearch. The
    contract under test: when every query call raises, ``search()``
    converts the failure to ``RetrievalUnavailable`` so callers
    (routes / agents) can surface a typed degraded state instead of
    swallowing the outage as "no results".
    """

    def search(self, **_):  # noqa: D401, ANN001
        raise RuntimeError("OpenSearch is down")


def test_search_raises_when_all_backend_calls_fail(monkeypatch):
    """Regression: previously every query exception was swallowed and
    ``search()`` returned ``[]``, so an OpenSearch outage looked like
    "no documents matched". The fix raises ``RetrievalUnavailable`` so
    the route layer can return 503 / SSE error events.
    """
    # Stub embedding so the test doesn't hit the real model loader.
    from src.retrieval import hybrid_search as hs

    monkeypatch.setattr(hs, "embed_query", lambda _q: [0.0] * 384)

    async def _run() -> None:
        engine = HybridSearchEngine(client=_FakeFailingClient())
        with pytest.raises(RetrievalUnavailable):
            await engine.search(requirement="anything", expand=False)

    asyncio.run(_run())


def test_search_partial_failure_returns_results(monkeypatch):
    """A single query failing should NOT take down retrieval; only an
    *all*-calls-failed run raises ``RetrievalUnavailable``. Here BM25
    raises but vector search returns valid hits, so the engine should
    still produce results.
    """
    from src.retrieval import hybrid_search as hs

    monkeypatch.setattr(hs, "embed_query", lambda _q: [0.0] * 384)

    class _PartialClient:
        def __init__(self):
            self.calls = 0

        def search(self, **_):  # noqa: ANN001
            self.calls += 1
            # First call (BM25) raises; later calls (vector) succeed
            # with an empty-but-valid response.
            if self.calls == 1:
                raise RuntimeError("transient bm25 failure")
            return {"hits": {"hits": []}}

    async def _run() -> None:
        engine = HybridSearchEngine(client=_PartialClient())
        # Should NOT raise -- the vector path succeeded.
        result = await engine.search(requirement="x", expand=False)
        assert isinstance(result, list)

    asyncio.run(_run())
