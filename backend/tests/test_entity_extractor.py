from src.ingestion.entity_extractor import _regex_fallback
from src.ingestion.team_names import canonicalize_team_name, extract_explicit_team_names


def test_canonicalize_team_name_merges_slug_and_case_variants():
    assert canonicalize_team_name("platform-team") == "Platform Team"
    assert canonicalize_team_name("platform team") == "Platform Team"
    assert canonicalize_team_name("qa team") == "QA Team"


def test_canonicalize_team_name_rejects_noise():
    assert canonicalize_team_name("See Team") is None
    assert canonicalize_team_name("With Team") is None
    assert canonicalize_team_name("Current Team") is None
    assert canonicalize_team_name("At Team") is None


def test_extract_explicit_team_names_prefers_real_team_mentions():
    content = """
    See team-roster.xlsx for current team composition.
    Meet with team lead and mentor.
    Owned by: platform-team
    This service is maintained by the Platform Team.
    """

    teams = extract_explicit_team_names(content, "gitlab/platform-team/api-gateway/README.md")
    assert teams == ["Platform Team"]


def test_regex_fallback_avoids_false_positive_team_phrases():
    content = """
    See team-roster.xlsx for current team composition.
    Meet with team lead and mentor.
    Headers: Name | Team | Role
    Name: Eve Garcia | Team: Platform Team | Role: Staff Engineer
    """

    extracted = _regex_fallback(content, "excel/team-roster.csv")
    assert [team["name"] for team in extracted.teams] == ["Platform Team"]
