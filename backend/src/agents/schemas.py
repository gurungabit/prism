from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RouterOutput(BaseModel):
    """Router picks a single primary owner. Team-to-team relationships live on
    ``DependencyOutput.upstream_teams`` / ``downstream_teams`` now -- the old
    ``supporting_teams`` field was redundant with team dependencies."""

    primary_team: TeamScore
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
    """Team-first dependency analysis.

    ``upstream_teams`` and ``downstream_teams`` are the first-class output --
    who the primary team needs to coordinate with, in what direction.
    The service-level lists (``blocking``/``impacted``/``informational``)
    are the secondary layer: which packages/services/CI paths create those
    team relationships.
    """

    upstream_teams: list[TeamDependency] = []
    downstream_teams: list[TeamDependency] = []
    blocking: list[DependencyItem] = []
    impacted: list[DependencyItem] = []
    informational: list[DependencyItem] = []
    reasoning: str = ""


class TeamDependency(BaseModel):
    """A team-to-team dependency relative to the primary team.

    ``upstream`` direction means the primary team depends on this team.
    ``downstream`` means this team depends on / will be impacted by the
    primary team's work.
    """

    team_name: str
    relationship: Literal["blocking", "impacted", "informational"] = "impacted"
    reason: str = ""
    # Specific services/packages/resources that make this team relevant.
    # The UI renders these on the edge detail panel so a reader can see
    # "why is security-team on the graph" at a glance.
    evidence_services: list[str] = []
    source_docs: list[str] = []


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


PlanMode = Literal["full", "chat"]


class PlanOutput(BaseModel):
    """Planner decision about which downstream agents to run.

    The planner is the orchestrator's one-shot classifier: it reads the
    requirement (plus any prior-thread context) and picks:

    - ``mode``: ``"full"`` runs the whole pipeline. ``"chat"`` skips agents
      and answers the question directly from prior context -- used for
      follow-ups that are clarifications/tweaks of an earlier analysis.
    - ``agents_to_run``: only relevant for ``mode == "full"``; retrieve +
      citations + synthesize always run, the four keys below are optional.
    """

    mode: PlanMode = "full"
    question_type: QuestionType
    agents_to_run: list[PlanAgentKey]
    reasoning: str = ""


class ChatAnswerOutput(BaseModel):
    """Short-answer output for ``mode == "chat"`` follow-ups."""

    answer: str
    # Paths the answer leans on. The UI linkifies them against the thread's
    # accumulated source map.
    cited_paths: list[str] = []


class RollingSummaryOutput(BaseModel):
    """One-paragraph memo of a completed run, fed back into future turns."""

    summary: str
