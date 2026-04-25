from uuid import UUID

from src.retrieval.hybrid_search import HybridSearchEngine, _build_scope_clauses


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
