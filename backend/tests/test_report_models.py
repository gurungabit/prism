from src.models.report import AnalysisInput, build_analysis_brief, build_search_query


def test_build_analysis_brief_includes_only_present_sections():
    analysis_input = AnalysisInput(
        requirement="Add MFA to customer portal",
        business_goal="Reduce account takeover risk",
        known_services="auth-service, customer-portal",
    )

    brief = build_analysis_brief(analysis_input)

    assert "REQUIREMENT:" in brief
    assert "BUSINESS GOAL:" in brief
    assert "KNOWN SERVICES:" in brief
    assert "CONSTRAINTS:" not in brief


def test_build_search_query_skips_blank_fields():
    analysis_input = AnalysisInput(
        requirement="Add MFA to customer portal",
        context="Coordinate with mobile launch",
        constraints="Do not break SSO",
    )

    query = build_search_query(analysis_input)

    assert "Add MFA to customer portal" in query
    assert "Coordinate with mobile launch" in query
    assert "Do not break SSO" in query
    assert "KNOWN TEAMS" not in query
