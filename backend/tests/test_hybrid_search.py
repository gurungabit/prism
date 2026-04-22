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
