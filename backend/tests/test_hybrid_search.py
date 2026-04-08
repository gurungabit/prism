from src.retrieval.hybrid_search import HybridSearchEngine


def test_build_filters_supports_scalar_values():
    engine = HybridSearchEngine(client=object())

    clauses = engine._build_filters({"doc_type": "readme", "source_platform": "gitlab"})

    assert clauses == [
        {"term": {"source_platform": "gitlab"}},
        {"term": {"doc_type": "readme"}},
    ]


def test_build_filters_supports_multi_select_values():
    engine = HybridSearchEngine(client=object())

    clauses = engine._build_filters(
        {
            "doc_type": ["readme", "wiki"],
            "team_hint": ["payments team"],
            "service_hint": [],
        },
    )

    assert clauses == [
        {"terms": {"doc_type": ["readme", "wiki"]}},
        {"terms": {"team_hint": ["payments team"]}},
    ]
