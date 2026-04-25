from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisInput(BaseModel):
    requirement: str
    business_goal: str = ""
    context: str = ""
    constraints: str = ""
    known_teams: str = ""
    known_services: str = ""
    questions_to_answer: str = ""
    # Scope for retrieval pushdown. ``org_id`` is required for scope to
    # apply at all -- it pins all retrieval to a single org's chunks. The
    # team / service lists are additional narrowing inside that org. Empty
    # lists mean "all teams / all services within the org". When ``org_id``
    # itself is None, retrieval falls back to the legacy un-scoped path.
    org_id: str | None = None
    team_ids: list[str] = Field(default_factory=list)
    service_ids: list[str] = Field(default_factory=list)


def build_analysis_brief(analysis_input: AnalysisInput) -> str:
    sections = [f"REQUIREMENT:\n{analysis_input.requirement.strip()}"]

    optional_sections = [
        ("BUSINESS GOAL", analysis_input.business_goal),
        ("ADDITIONAL CONTEXT", analysis_input.context),
        ("CONSTRAINTS", analysis_input.constraints),
        ("KNOWN TEAMS", analysis_input.known_teams),
        ("KNOWN SERVICES", analysis_input.known_services),
        ("QUESTIONS TO ANSWER", analysis_input.questions_to_answer),
    ]

    for title, value in optional_sections:
        if value.strip():
            sections.append(f"{title}:\n{value.strip()}")

    return "\n\n".join(sections)


def build_search_query(analysis_input: AnalysisInput) -> str:
    parts = [
        analysis_input.requirement.strip(),
        analysis_input.business_goal.strip(),
        analysis_input.context.strip(),
        analysis_input.constraints.strip(),
        analysis_input.known_teams.strip(),
        analysis_input.known_services.strip(),
        analysis_input.questions_to_answer.strip(),
    ]
    return "\n".join(part for part in parts if part)


class Citation(BaseModel):
    document_path: str
    # Clickable URL to the original document when the connector provides one
    # (e.g. GitLab blob URL). Empty for local/file-based platforms.
    source_url: str = ""
    excerpt: str = ""
    last_modified: str = ""
    relevance_score: float = 0.0


class TeamCandidate(BaseModel):
    name: str
    confidence: float
    justification: str
    role: str = "primary"
    sources: list[Citation] = []


class TeamRouting(BaseModel):
    primary_team: TeamCandidate
    # Legacy field kept for JSON compatibility with pre-blast-radius stored
    # reports; new reports leave this empty and use team_blast_radius instead.
    supporting_teams: list[TeamCandidate] = []


class AffectedService(BaseModel):
    name: str
    impact: Literal["direct", "indirect", "informational"]
    owning_team: str = ""
    changes_needed: str = ""
    sources: list[Citation] = []


class DependencyEdge(BaseModel):
    from_service: str
    to_service: str
    dependency_type: Literal["blocking", "impacted", "informational"]
    reason: str = ""
    sources: list[Citation] = []


class DependencyTree(BaseModel):
    blocking: list[DependencyEdge] = []
    impacted: list[DependencyEdge] = []
    informational: list[DependencyEdge] = []


class TeamDependencyEdge(BaseModel):
    """Team-to-team relationship relative to the primary team."""

    team_name: str
    relationship: Literal["blocking", "impacted", "informational"] = "impacted"
    reason: str = ""
    evidence_services: list[str] = []
    sources: list[Citation] = []


class TeamBlastRadius(BaseModel):
    """Blast radius of a requirement in team terms. ``upstream`` teams must be
    coordinated with before/during the work; ``downstream`` teams are
    affected by the output and may need to adapt."""

    upstream: list[TeamDependencyEdge] = []
    downstream: list[TeamDependencyEdge] = []


class RiskItem(BaseModel):
    category: Literal[
        "technical_complexity",
        "dependency_risk",
        "knowledge_gaps",
        "integration_risk",
        "data_risk",
        "security_risk",
    ]
    level: Literal["low", "medium", "high", "critical"]
    description: str
    mitigation: str = ""
    sources: list[Citation] = []


class RiskAssessment(BaseModel):
    overall_risk: Literal["low", "medium", "high", "critical"]
    risks: list[RiskItem] = []


class EffortBreakdown(BaseModel):
    task: str
    days_min: int
    days_max: int
    team: str


class StaffingEstimate(BaseModel):
    engineers_needed: int
    reviewers_needed: int
    estimated_calendar_weeks_min: int
    estimated_calendar_weeks_max: int


class EffortEstimate(BaseModel):
    total_days_min: int
    total_days_max: int
    confidence: Literal["low", "medium", "high"]
    breakdown: list[EffortBreakdown] = []
    staffing: StaffingEstimate | None = None
    sources: list[Citation] = []


class ConflictClaimant(BaseModel):
    team: str
    confidence: Literal["explicit", "inferred"]
    source: str
    updated: str


class OwnershipConflict(BaseModel):
    service: str
    claimed_by: list[ConflictClaimant] = []
    resolution: str = ""


class SourceDocument(BaseModel):
    id: str
    path: str
    platform: str
    source_url: str = ""
    relevance_score: float = 0.0
    last_modified: str = ""
    is_stale: bool = False
    sections_cited: list[str] = []


class CoverageReport(BaseModel):
    documents_retrieved: int = 0
    documents_cited: int = 0
    platforms_searched: list[str] = []
    gaps: list[str] = []
    critical_gaps: list[str] = []
    stale_sources: list[str] = []
    retrieval_rounds: int = 0


class VerifiedClaim(BaseModel):
    claim: str
    supporting_doc: str
    excerpt: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class VerificationReport(BaseModel):
    verified_claims: list[VerifiedClaim] = []
    unsupported_claims: list[str] = []
    stale_source_warnings: list[str] = []


class ImpactMatrixRow(BaseModel):
    team: str
    service: str
    role: str = ""
    why_involved: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    blocker: str = ""
    evidence: list[str] = []


class PRISMReport(BaseModel):
    analysis_id: str
    requirement: str
    analysis_input: AnalysisInput | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0
    executive_summary: str = ""
    team_routing_narrative: str = ""
    dependency_narrative: str = ""
    risk_narrative: str = ""
    effort_narrative: str = ""
    data_quality_summary: str = ""
    recommendations: list[str] = []
    caveats: list[str] = []
    team_routing: TeamRouting | None = None
    affected_services: list[AffectedService] = []
    # Team blast radius: who the primary team coordinates with (upstream)
    # and who consumes / is impacted by their output (downstream).
    team_blast_radius: TeamBlastRadius = TeamBlastRadius()
    dependencies: DependencyTree = DependencyTree()
    risk_assessment: RiskAssessment | None = None
    effort_estimate: EffortEstimate | None = None
    conflicts_detected: list[OwnershipConflict] = []
    staleness_warnings: list[str] = []
    coverage_report: CoverageReport = CoverageReport()
    verification_report: VerificationReport = VerificationReport()
    impact_matrix: list[ImpactMatrixRow] = []
    all_sources: list[SourceDocument] = []
