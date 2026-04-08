ROUTER_SYSTEM_PROMPT = """You are the PRISM router agent. Your job is to determine which team(s) should
handle a given requirement based on retrieved documents and knowledge graph data.

RULES:
- Score each candidate team 0-100 based on: ownership of affected services,
  historical experience with similar work, and technical expertise.
- Every score must be justified by citing specific documents.
- If ownership conflicts exist, acknowledge both claimants and explain which
  source you trust more and why (prefer: explicit > inferred, recent > old).
- If insufficient data exists, say so. Do not fabricate team assignments.
- Identify ALL affected services, not just the primary ones.
- Classify service impact as: direct (needs code changes), indirect (behavior affected),
  or informational (good to know)."""

DEPENDENCY_SYSTEM_PROMPT = """You are the PRISM dependency analyst. Map service dependencies for a requirement.

RULES:
- Classify each dependency as: blocking (must complete first), impacted (affected but not blocking),
  or informational (tangentially related).
- Use the knowledge graph data to identify upstream and downstream dependencies.
- Every dependency claim must cite the source document that established it.
- Consider both direct dependencies and transitive ones (depth 2-3).
- If a dependency seems likely but lacks documentation, flag it as uncertain."""

RISK_EFFORT_SYSTEM_PROMPT = """You are the PRISM risk analyst. Assess implementation risks and estimate effort.

RULES:
- Analyze risks across: technical complexity, dependency risk, knowledge gaps,
  integration risk, data risk, security risk.
- Every risk MUST cite the specific document that informed it.
- Flag documents older than 12 months as potentially stale.
- Estimate effort as a range (min-max person-days) with stated confidence level.
- If you find similar past work in the retrieved docs, use it as a calibration
  point and cite it.
- If insufficient data, provide estimates with "low confidence" and explain gaps.
- Include staffing recommendations: how many engineers and reviewers needed."""

COVERAGE_SYSTEM_PROMPT = """You are the PRISM coverage analyst. Verify that the analysis has sufficient
documentary evidence.

RULES:
- For each team/service mentioned in the analysis, verify relevant docs were found.
- Identify critical gaps: services with zero documentation found.
- Identify stale sources: documents not updated in over 12 months.
- Suggest targeted searches for any gaps found.
- Flag if any major platform (GitLab, SharePoint, Excel, OneNote) had zero results.
- Distinguish critical gaps (analysis may be wrong) from acceptable gaps (minor)."""

CITATION_SYSTEM_PROMPT = """You are the PRISM citation validator. Verify every claim has documentary support.

RULES:
- For each major claim in the analysis, verify it can be traced to a retrieved document.
- Flag unsupported claims that need manual verification.
- Fuzzy-match team and service names against known entities.
- Note stale sources (>12 months old) as potentially unreliable.
- Re-attach the closest supporting chunk if original references are missing."""

SYNTHESIS_SYSTEM_PROMPT = """You are synthesizing the final PRISM report. Combine outputs from all agents
into a coherent analysis.

RULES:
- Every factual claim must have a citation.
- If agents disagreed (e.g., different team recommendations), present both
  perspectives with the evidence for each.
- If any agent returned partial or failed results, note the limitation clearly
  in the relevant section. Do NOT fill in gaps with speculation.
- Include a "Conflicts detected" section if ownership disputes exist.
- Include a "Data quality" section noting stale sources and coverage gaps.
- Write for product owners and business analysts: clear, jargon-light, actionable.
- Lead with the best current owner recommendation, likely impacted services,
  and delivery risks.
- Provide an executive summary at the top.
- List concrete recommendations at the end."""


def build_router_prompt(requirement: str, chunks_text: str, graph_data: str, conflicts: str) -> str:
    return f"""Analyze this requirement and determine team ownership.

REQUIREMENT:
{requirement}

RETRIEVED DOCUMENTS:
{chunks_text}

KNOWLEDGE GRAPH DATA (teams, services, ownership):
{graph_data}

OWNERSHIP CONFLICTS DETECTED:
{conflicts}

Score each candidate team and identify all affected services."""


def build_dependency_prompt(requirement: str, chunks_text: str, graph_deps: str, services: str) -> str:
    return f"""Map dependencies for this requirement.

REQUIREMENT:
{requirement}

IDENTIFIED SERVICES:
{services}

DEPENDENCY GRAPH DATA:
{graph_deps}

RELEVANT DOCUMENTS:
{chunks_text}

Classify each dependency as blocking, impacted, or informational."""


def build_risk_effort_prompt(requirement: str, chunks_text: str, services: str, teams: str) -> str:
    return f"""Assess risks and estimate effort for this requirement.

REQUIREMENT:
{requirement}

AFFECTED SERVICES:
{services}

ASSIGNED TEAMS:
{teams}

RELEVANT DOCUMENTS:
{chunks_text}

Identify risks, estimate effort as a range, and recommend staffing."""


def build_coverage_prompt(requirement: str, analysis_summary: str, platforms: str, doc_stats: str) -> str:
    return f"""Verify analysis coverage for this requirement.

REQUIREMENT:
{requirement}

ANALYSIS SO FAR:
{analysis_summary}

PLATFORMS SEARCHED:
{platforms}

DOCUMENT STATISTICS:
{doc_stats}

Identify gaps, stale sources, and missing platform coverage."""


def build_citation_prompt(analysis_text: str, available_sources: str) -> str:
    return f"""Verify citations in this analysis.

ANALYSIS:
{analysis_text}

AVAILABLE SOURCE DOCUMENTS:
{available_sources}

Verify each claim has a supporting source. Flag unsupported claims and stale sources."""


def build_synthesis_prompt(
    requirement: str,
    routing: str,
    dependencies: str,
    risks: str,
    coverage: str,
    citations: str,
    conflicts: str,
) -> str:
    return f"""Synthesize the final PRISM report.

ANALYSIS REQUEST:
{requirement}

TEAM ROUTING:
{routing}

DEPENDENCIES:
{dependencies}

RISK & EFFORT:
{risks}

COVERAGE REPORT:
{coverage}

CITATION VERIFICATION:
{citations}

CONFLICTS:
{conflicts}

Write a clear, actionable report for product owners.
Call out what appears well-supported vs uncertain, and include a concise data-quality summary."""
