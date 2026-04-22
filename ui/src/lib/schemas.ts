import { z } from "zod";

// ── Analysis Input ────────────────────────────────────

export const AnalysisInputSchema = z.object({
  requirement: z.string(),
  business_goal: z.string().default(""),
  context: z.string().default(""),
  constraints: z.string().default(""),
  known_teams: z.string().default(""),
  known_services: z.string().default(""),
  questions_to_answer: z.string().default(""),
});

// ── Citations & Sources ───────────────────────────────

export const CitationSchema = z.object({
  document_path: z.string(),
  source_url: z.string().default(""),
  excerpt: z.string().default(""),
  last_modified: z.string().default(""),
  relevance_score: z.number().default(0),
});

export const SourceDocumentSchema = z.object({
  id: z.string(),
  path: z.string(),
  platform: z.string(),
  source_url: z.string().default(""),
  relevance_score: z.number().default(0),
  last_modified: z.string().default(""),
  is_stale: z.boolean().default(false),
  sections_cited: z.array(z.string()).default([]),
});

// ── Team Routing ──────────────────────────────────────

export const TeamCandidateSchema = z.object({
  name: z.string(),
  confidence: z.number(),
  justification: z.string(),
  role: z.string().default("primary"),
  sources: z.array(CitationSchema).default([]),
});

export const TeamRoutingSchema = z.object({
  primary_team: TeamCandidateSchema,
  supporting_teams: z.array(TeamCandidateSchema).default([]),
});

// ── Services ──────────────────────────────────────────

export const AffectedServiceSchema = z.object({
  name: z.string(),
  impact: z.enum(["direct", "indirect", "informational"]),
  owning_team: z.string().default(""),
  changes_needed: z.string().default(""),
  sources: z.array(CitationSchema).default([]),
});

// ── Dependencies ──────────────────────────────────────

export const DependencyEdgeSchema = z.object({
  from_service: z.string(),
  to_service: z.string(),
  dependency_type: z.enum(["blocking", "impacted", "informational"]),
  reason: z.string().default(""),
  sources: z.array(CitationSchema).default([]),
});

export const DependencyTreeSchema = z.object({
  blocking: z.array(DependencyEdgeSchema).default([]),
  impacted: z.array(DependencyEdgeSchema).default([]),
  informational: z.array(DependencyEdgeSchema).default([]),
});

// ── Risk ──────────────────────────────────────────────

const RiskCategory = z.enum([
  "technical_complexity",
  "dependency_risk",
  "knowledge_gaps",
  "integration_risk",
  "data_risk",
  "security_risk",
]);

const RiskLevel = z.enum(["low", "medium", "high", "critical"]);

export const RiskItemSchema = z.object({
  category: RiskCategory,
  level: RiskLevel,
  description: z.string(),
  mitigation: z.string().default(""),
  sources: z.array(CitationSchema).default([]),
});

export const RiskAssessmentSchema = z.object({
  overall_risk: RiskLevel,
  risks: z.array(RiskItemSchema).default([]),
});

// ── Effort ────────────────────────────────────────────

export const EffortBreakdownSchema = z.object({
  task: z.string(),
  days_min: z.number(),
  days_max: z.number(),
  team: z.string(),
});

export const StaffingEstimateSchema = z.object({
  engineers_needed: z.number(),
  reviewers_needed: z.number(),
  estimated_calendar_weeks_min: z.number(),
  estimated_calendar_weeks_max: z.number(),
});

export const EffortEstimateSchema = z.object({
  total_days_min: z.number(),
  total_days_max: z.number(),
  confidence: z.enum(["low", "medium", "high"]),
  breakdown: z.array(EffortBreakdownSchema).default([]),
  staffing: StaffingEstimateSchema.nullable().default(null),
  sources: z.array(CitationSchema).default([]),
});

// ── Conflicts ─────────────────────────────────────────

export const ConflictClaimantSchema = z.object({
  team: z.string(),
  confidence: z.enum(["explicit", "inferred"]),
  source: z.string(),
  updated: z.string(),
});

export const OwnershipConflictSchema = z.object({
  service: z.string(),
  claimed_by: z.array(ConflictClaimantSchema).default([]),
  resolution: z.string().default(""),
});

// ── Coverage ──────────────────────────────────────────

export const CoverageReportSchema = z.object({
  documents_retrieved: z.number().default(0),
  documents_cited: z.number().default(0),
  platforms_searched: z.array(z.string()).default([]),
  gaps: z.array(z.string()).default([]),
  critical_gaps: z.array(z.string()).default([]),
  stale_sources: z.array(z.string()).default([]),
  retrieval_rounds: z.number().default(0),
});

export const VerifiedClaimSchema = z.object({
  claim: z.string(),
  supporting_doc: z.string(),
  excerpt: z.string().default(""),
  confidence: z.enum(["high", "medium", "low"]).default("medium"),
});

export const VerificationReportSchema = z.object({
  verified_claims: z.array(VerifiedClaimSchema).default([]),
  unsupported_claims: z.array(z.string()).default([]),
  stale_source_warnings: z.array(z.string()).default([]),
});

export const ImpactMatrixRowSchema = z.object({
  team: z.string(),
  service: z.string(),
  role: z.string().default(""),
  why_involved: z.string().default(""),
  confidence: z.enum(["high", "medium", "low"]).default("medium"),
  blocker: z.string().default(""),
  evidence: z.array(z.string()).default([]),
});

// ── Full Report ───────────────────────────────────────

export const PRISMReportSchema = z.object({
  analysis_id: z.string(),
  requirement: z.string(),
  analysis_input: AnalysisInputSchema.nullable().default(null),
  created_at: z.string(),
  duration_seconds: z.number().default(0),
  executive_summary: z.string().default(""),
  team_routing_narrative: z.string().default(""),
  dependency_narrative: z.string().default(""),
  risk_narrative: z.string().default(""),
  effort_narrative: z.string().default(""),
  data_quality_summary: z.string().default(""),
  recommendations: z.array(z.string()).default([]),
  caveats: z.array(z.string()).default([]),
  team_routing: TeamRoutingSchema.nullable().default(null),
  affected_services: z.array(AffectedServiceSchema).default([]),
  dependencies: DependencyTreeSchema.default({}),
  risk_assessment: RiskAssessmentSchema.nullable().default(null),
  effort_estimate: EffortEstimateSchema.nullable().default(null),
  conflicts_detected: z.array(OwnershipConflictSchema).default([]),
  staleness_warnings: z.array(z.string()).default([]),
  coverage_report: CoverageReportSchema.default({}),
  verification_report: VerificationReportSchema.default({}),
  impact_matrix: z.array(ImpactMatrixRowSchema).default([]),
  all_sources: z.array(SourceDocumentSchema).default([]),
});

export type PRISMReport = z.infer<typeof PRISMReportSchema>;

// ── SSE Events ────────────────────────────────────────

export const AgentStepEventSchema = z.object({
  type: z.literal("agent_step"),
  id: z.string(),
  agent: z.string(),
  action: z.string(),
  detail: z.string().default(""),
  data: z.unknown().optional(),
  timestamp: z.number(),
});

export const CompleteEventSchema = z.object({
  type: z.literal("complete"),
  id: z.string(),
  report: PRISMReportSchema.optional(),
  error: z.string().optional(),
  timestamp: z.number(),
});

export const ErrorEventSchema = z.object({
  type: z.literal("error"),
  id: z.string(),
  error: z.string(),
  timestamp: z.number(),
});

export const SSEEventSchema = z.discriminatedUnion("type", [
  AgentStepEventSchema,
  CompleteEventSchema,
  ErrorEventSchema,
]);

export type AgentStepEvent = z.infer<typeof AgentStepEventSchema>;
export type SSEEvent = z.infer<typeof SSEEventSchema>;

// ── Search ────────────────────────────────────────────

export const SearchResultSchema = z.object({
  chunk_id: z.string(),
  content: z.string(),
  score: z.number(),
  source_path: z.string(),
  document_title: z.string(),
  doc_type: z.string(),
  platform: z.string(),
});

export const SearchResponseSchema = z.object({
  query: z.string(),
  results: z.array(SearchResultSchema),
  page: z.number(),
  page_size: z.number(),
  has_more: z.boolean(),
  total: z.number().nullable().default(null),
});

export type SearchResult = z.infer<typeof SearchResultSchema>;

// ── History ───────────────────────────────────────────

export const HistoryEntrySchema = z.object({
  analysis_id: z.string(),
  requirement: z.string(),
  status: z.string(),
  created_at: z.string(),
  duration_seconds: z.number().nullable().default(null),
});

export const HistoryResponseSchema = z.object({
  analyses: z.array(HistoryEntrySchema),
  total: z.number(),
});

export type HistoryEntry = z.infer<typeof HistoryEntrySchema>;

// ── Sources listing ───────────────────────────────────

export const SourceDocListSchema = z.object({
  document_id: z.string(),
  source_path: z.string(),
  chunk_count: z.number().default(0),
  status: z.string().default("unknown"),
  last_ingested_at: z.string().nullable().default(null),
});

export const SourceGroupSchema = z.object({
  platform: z.string(),
  document_count: z.number(),
  last_ingested: z.string().nullable().default(null),
  documents: z.array(SourceDocListSchema).default([]),
});

export const SourcesResponseSchema = z.object({
  sources: z.array(SourceGroupSchema),
  total: z.number(),
});

export type SourceGroup = z.infer<typeof SourceGroupSchema>;
export type SourceDocList = z.infer<typeof SourceDocListSchema>;

// ── Chat ──────────────────────────────────────────────

export const ChatMessageSchema = z.object({
  role: z.string(),
  content: z.string(),
  citations: z.array(
    z.object({
      index: z.number(),
      title: z.string(),
      platform: z.string(),
      source_path: z.string(),
      source_url: z.string().optional(),
      section_heading: z.string().optional(),
      score: z.number().optional(),
      content: z.string().optional(),
      excerpt: z.string().optional(),
    }),
  ).optional(),
});

export const ConversationListItemSchema = z.object({
  conversation_id: z.string(),
  message_count: z.number(),
  last_message: z.string().default(""),
  preview: z.string().default(""),
});

export const ConversationDetailSchema = z.object({
  conversation_id: z.string(),
  messages: z.array(ChatMessageSchema),
});

export const ConversationsResponseSchema = z.object({
  conversations: z.array(ConversationListItemSchema),
});

export type ConversationListItem = z.infer<typeof ConversationListItemSchema>;
export type ConversationDetail = z.infer<typeof ConversationDetailSchema>;
