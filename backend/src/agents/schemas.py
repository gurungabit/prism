from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RouterOutput(BaseModel):
    primary_team: TeamScore
    supporting_teams: list[TeamScore] = []
    affected_services: list[ServiceImpact] = []
    reasoning: str = ""


class TeamScore(BaseModel):
    name: str
    confidence: float
    justification: str
    role: str = "primary"
    key_sources: list[str] = []


class ServiceImpact(BaseModel):
    name: str
    impact: Literal["direct", "indirect", "informational"]
    changes_needed: str = ""
    owning_team: str = ""
    source_docs: list[str] = []


class DependencyOutput(BaseModel):
    blocking: list[DependencyItem] = []
    impacted: list[DependencyItem] = []
    informational: list[DependencyItem] = []
    reasoning: str = ""


class DependencyItem(BaseModel):
    from_service: str
    to_service: str
    reason: str = ""
    source_docs: list[str] = []


class RiskEffortOutput(BaseModel):
    overall_risk: Literal["low", "medium", "high", "critical"]
    risks: list[RiskItemOutput] = []
    total_days_min: int = 0
    total_days_max: int = 0
    effort_confidence: Literal["low", "medium", "high"] = "low"
    effort_breakdown: list[EffortItem] = []
    staffing_engineers: int = 1
    staffing_reviewers: int = 1
    calendar_weeks_min: int = 1
    calendar_weeks_max: int = 4
    reasoning: str = ""


class RiskItemOutput(BaseModel):
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
    source_docs: list[str] = []


class EffortItem(BaseModel):
    task: str
    days_min: int
    days_max: int
    team: str


class CoverageOutput(BaseModel):
    documents_retrieved: int = 0
    documents_cited: int = 0
    platforms_searched: list[str] = []
    gaps: list[str] = []
    critical_gaps: list[str] = []
    stale_sources: list[str] = []
    reasoning: str = ""


class CitationVerification(BaseModel):
    verified_claims: list[VerifiedClaim] = []
    unsupported_claims: list[str] = []
    stale_source_warnings: list[str] = []


class VerifiedClaim(BaseModel):
    claim: str
    supporting_doc: str
    excerpt: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class SynthesisOutput(BaseModel):
    executive_summary: str
    team_routing_narrative: str
    dependency_narrative: str
    risk_narrative: str
    effort_narrative: str
    data_quality_summary: str = ""
    recommendations: list[str] = []
    caveats: list[str] = []


# Keys must match the orchestrator's downstream node names so the planner
# can gate them directly by name. "router" is the agent name even though the
# node is called "route".
PlanAgentKey = Literal["router", "dependencies", "risk_effort", "coverage"]

QuestionType = Literal[
    "ownership",
    "dependency",
    "risk_effort",
    "coverage",
    "impact",
    "general",
]


class PlanOutput(BaseModel):
    """Planner decision about which downstream agents to run.

    The planner is the orchestrator's one-shot classifier: it reads the
    requirement and picks which sub-agents are worth paying for. Retrieve +
    citations + synthesize always run -- they're the backbone. The four keys
    below can each be skipped when the question doesn't need them.
    """

    question_type: QuestionType
    agents_to_run: list[PlanAgentKey]
    reasoning: str = ""
