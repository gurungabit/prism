const BASE_URL = import.meta.env.VITE_API_URL || "";

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }

  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
  ) {
    super(`API ${status}: ${body}`);
    this.name = "ApiError";
  }
}

// ── Analysis ──────────────────────────────────────────

export interface AnalysisInput {
  requirement: string;
  business_goal?: string;
  context?: string;
  constraints?: string;
  known_teams?: string;
  known_services?: string;
  questions_to_answer?: string;
  // Threading: present on follow-ups to link the new run into an existing
  // thread. ``force_full`` makes a follow-up run a full analysis even when
  // the planner would otherwise pick chat mode.
  parent_analysis_id?: string;
  force_full?: boolean;
}

export function startAnalysis(input: AnalysisInput) {
  return request<{ analysis_id: string; thread_id: string; stream_url: string }>(
    "/api/analyze",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function getReport(analysisId: string) {
  return request<Record<string, unknown>>(`/api/analyze/${analysisId}/report`);
}

export function getTrace(analysisId: string) {
  return request<{ analysis_id: string; trace: unknown[] }>(
    `/api/analyze/${analysisId}/trace`,
  );
}

export function getSources(analysisId: string) {
  return request<{ sources: unknown[] }>(
    `/api/analyze/${analysisId}/sources`,
  );
}

export function submitFeedback(
  analysisId: string,
  data: { section: string; correct_answer: string; reason?: string },
) {
  return request<{ status: string; message: string }>(
    `/api/analyze/${analysisId}/feedback`,
    { method: "POST", body: JSON.stringify(data) },
  );
}

// ── Search ────────────────────────────────────────────

export interface SearchParams {
  query: string;
  filters?: Record<string, unknown>;
  page?: number;
  page_size?: number;
  top_k?: number;
  scope?: {
    org_id?: string;
    team_ids?: string[];
    service_ids?: string[];
  };
}

export interface SearchResult {
  chunk_id: string;
  content: string;
  score: number;
  source_path: string;
  document_title: string;
  doc_type: string;
  platform: string;
  org_id?: string | null;
  team_id?: string | null;
  service_id?: string | null;
}

export function searchDocuments(params: SearchParams) {
  return request<{
    query: string;
    results: SearchResult[];
    page: number;
    page_size: number;
    has_more: boolean;
    total: number | null;
  }>(
    "/api/search",
    { method: "POST", body: JSON.stringify(params) },
  );
}

// ── Graph ─────────────────────────────────────────────

export interface TeamData {
  team: string;
  team_id?: string;
  org_id?: string;
  description?: string;
  services: string[];
}

export function getTeams() {
  return request<{ teams: TeamData[] }>("/api/graph/teams");
}

export function getTeamProfile(teamName: string) {
  return request<Record<string, unknown>>(`/api/graph/teams/${teamName}`);
}

export function getService(serviceName: string) {
  return request<Record<string, unknown>>(
    `/api/graph/services/${serviceName}`,
  );
}

export function getDependencies(serviceName: string, depth = 2) {
  return request<Record<string, unknown>>(
    `/api/graph/dependencies/${serviceName}?depth=${depth}`,
  );
}

// ── Health ────────────────────────────────────────────

export function healthCheck() {
  return request<{ status: string; service: string }>("/api/health");
}

// ── History (threads) ─────────────────────────────────

export interface ThreadSummary {
  thread_id: string;
  turn_count: number;
  started_at: string;
  last_turn_at: string;
  requirement: string;
  // 4-8 word headline from the planner's title step. Empty if the title
  // task hasn't completed (or this is an old row).
  title: string;
  status: string;
  duration_seconds: number | null;
}

export function getHistory(limit = 20, offset = 0) {
  return request<{ threads: ThreadSummary[]; total: number }>(
    `/api/history?limit=${limit}&offset=${offset}`,
  );
}

export function deleteAnalysis(analysisId: string) {
  return request<{ status: string; analysis_id: string }>(
    `/api/history/${analysisId}`,
    { method: "DELETE" },
  );
}

// ── Threads (multi-turn analyses) ─────────────────────

export interface ThreadTurnReport {
  // PRISMReport shape, plus chat-turn extras the backend adds before
  // persisting. We keep the type loose here and let the UI branch on kind.
  [k: string]: unknown;
  chat_answer?: { answer: string; cited_paths: string[] };
}

export interface ThreadTurn {
  analysis_id: string;
  parent_analysis_id: string | null;
  // ``pending`` = planner hasn't decided yet; becomes ``full`` or ``chat``
  // once the planner resolves. The UI renders a lightweight loading state
  // for pending turns so follow-ups don't flash the full pipeline view.
  kind: "full" | "chat" | "pending";
  requirement: string;
  // 4-8 word LLM-generated headline. Empty until the planner's title task
  // writes it back; UI falls back to ``requirement`` while empty.
  title: string;
  status: string;
  created_at: string | null;
  duration_seconds: number | null;
  rolling_summary: string;
  report: ThreadTurnReport | null;
}

export function getThread(threadIdOrRunId: string) {
  return request<{ thread_id: string; turns: ThreadTurn[] }>(
    `/api/threads/${threadIdOrRunId}`,
  );
}

export function resolveAnalysisThread(analysisId: string) {
  return request<{ analysis_id: string; thread_id: string }>(
    `/api/analyze/resolve/${analysisId}`,
  );
}

// ── Catalog: orgs / teams / services ─────────────────

export interface Organization {
  id: string;
  name: string;
  created_at: string;
}

export interface Team {
  id: string;
  org_id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface Service {
  id: string;
  team_id: string;
  name: string;
  repo_url: string;
  description: string;
  created_at: string;
}

export function listOrgs() {
  return request<{ orgs: Organization[] }>("/api/orgs");
}

export function getOrg(orgId: string) {
  return request<Organization>(`/api/orgs/${orgId}`);
}

export function createOrg(name: string) {
  return request<Organization>("/api/orgs", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateOrg(orgId: string, name: string) {
  return request<Organization>(`/api/orgs/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteOrg(orgId: string) {
  return request<{ status: string }>(`/api/orgs/${orgId}`, { method: "DELETE" });
}

export function listTeamsForOrg(orgId: string) {
  return request<{ teams: Team[] }>(`/api/orgs/${orgId}/teams`);
}

export function getTeam(teamId: string) {
  return request<Team>(`/api/teams/${teamId}`);
}

export function createTeam(orgId: string, body: { name: string; description?: string }) {
  return request<Team>(`/api/orgs/${orgId}/teams`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateTeam(
  teamId: string,
  body: { name?: string; description?: string },
) {
  return request<Team>(`/api/teams/${teamId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteTeam(teamId: string) {
  return request<{ status: string }>(`/api/teams/${teamId}`, { method: "DELETE" });
}

export function listServicesForTeam(teamId: string) {
  return request<{ services: Service[] }>(`/api/teams/${teamId}/services`);
}

export function getServiceById(serviceId: string) {
  return request<Service>(`/api/services/${serviceId}`);
}

export function createService(
  teamId: string,
  body: { name: string; repo_url?: string; description?: string },
) {
  return request<Service>(`/api/teams/${teamId}/services`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateService(
  serviceId: string,
  body: { name?: string; repo_url?: string; description?: string },
) {
  return request<Service>(`/api/services/${serviceId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteService(serviceId: string) {
  return request<{ status: string }>(`/api/services/${serviceId}`, { method: "DELETE" });
}

// ── Catalog: sources ─────────────────────────────────

export type SourceScope = "org" | "team" | "service";
export type SourceKind = "gitlab" | "sharepoint" | "excel" | "onenote";
export type SourceStatus = "pending" | "syncing" | "ready" | "error";

export interface DeclaredSource {
  id: string;
  org_id: string | null;
  team_id: string | null;
  service_id: string | null;
  kind: SourceKind;
  name: string;
  config: Record<string, unknown>;
  secret_ref: string | null;
  status: SourceStatus;
  last_ingested_at: string | null;
  last_error: string | null;
  created_at: string;
  document_count?: number;
}

export interface SourceDocument {
  document_id: string;
  source_path: string;
  chunk_count: number;
  status: string;
  last_ingested_at: string | null;
  source_platform: string;
  title: string | null;
  source_url: string | null;
}

export function listDeclaredSources(params?: {
  orgId?: string;
  teamId?: string;
  serviceId?: string;
}) {
  const query = new URLSearchParams();
  if (params?.orgId) query.set("org_id", params.orgId);
  if (params?.teamId) query.set("team_id", params.teamId);
  if (params?.serviceId) query.set("service_id", params.serviceId);
  const qs = query.toString();
  return request<{ sources: DeclaredSource[]; total: number }>(
    `/api/sources${qs ? `?${qs}` : ""}`,
  );
}

export function getDeclaredSource(sourceId: string) {
  return request<DeclaredSource & { documents: SourceDocument[] }>(
    `/api/sources/${sourceId}`,
  );
}

export function getSourceStatus(sourceId: string) {
  return request<{
    source_id: string;
    status: SourceStatus;
    last_ingested_at: string | null;
    last_error: string | null;
  }>(`/api/sources/${sourceId}/status`);
}

export interface CreateSourceBody {
  scope: SourceScope;
  scope_id: string;
  kind: SourceKind;
  name: string;
  config: Record<string, unknown>;
  token?: string;
}

export function createSource(body: CreateSourceBody) {
  return request<DeclaredSource>("/api/sources", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSource(
  sourceId: string,
  body: { name?: string; config?: Record<string, unknown>; token?: string },
) {
  return request<DeclaredSource>(`/api/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteSource(sourceId: string) {
  return request<{ status: string }>(`/api/sources/${sourceId}`, { method: "DELETE" });
}

export function triggerSourceIngest(sourceId: string, force = false) {
  return request<{ status: string; source_id: string; force: boolean }>(
    `/api/sources/${sourceId}/ingest?force=${force}`,
    { method: "POST" },
  );
}

export interface ValidateSourceBody {
  kind: SourceKind;
  config: Record<string, unknown>;
  token?: string;
}

export function validateSource(body: ValidateSourceBody) {
  return request<{
    ok: boolean;
    kind: SourceKind;
    projects?: Array<{
      id: number;
      path_with_namespace: string;
      web_url: string;
      default_branch: string | null;
    }>;
    total_projects?: number;
    path?: string;
  }>("/api/sources/validate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface GitLabProject {
  id: number;
  path_with_namespace: string;
  name: string;
  web_url: string;
  default_branch: string | null;
}

export interface SearchGitlabProjectsBody {
  base_url?: string;
  token?: string;
  q?: string;
  page?: number;
  per_page?: number;
}

export interface OrganizationGraphResponse {
  orgs: Array<{ id: string; name: string; created_at: string }>;
  teams: Array<{
    id: string;
    org_id: string;
    name: string;
    description: string;
    created_at: string;
  }>;
  services: Array<{
    id: string;
    team_id: string;
    name: string;
    repo_url: string;
    description: string;
    created_at: string;
  }>;
  dependencies: Array<{
    from_service_id: string;
    to_service_id: string;
    from_service: string;
    to_service: string;
    source: string;
  }>;
}

export function getOrganizationGraph() {
  return request<OrganizationGraphResponse>("/api/organization/graph");
}

export function searchGitlabProjects(body: SearchGitlabProjectsBody) {
  return request<{
    projects: GitLabProject[];
    page: number;
    per_page: number;
    has_more: boolean;
  }>("/api/gitlab/projects/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface GitLabGroup {
  id: number;
  full_path: string;
  name: string;
  web_url: string;
}

export function searchGitlabGroups(body: SearchGitlabProjectsBody) {
  return request<{
    groups: GitLabGroup[];
    page: number;
    per_page: number;
    has_more: boolean;
  }>("/api/gitlab/groups/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Chat ─────────────────────────────────────────────

export interface ChatConversation {
  conversation_id: string;
  message_count: number;
  last_message: string;
  preview: string;
}

export interface ChatMessageData {
  role: string;
  content: string;
  citations?: Array<{
    index: number;
    title: string;
    platform: string;
    source_path: string;
    source_url?: string;
    section_heading?: string;
    score?: number;
    content?: string;
    excerpt?: string;
  }>;
}

export function getConversations() {
  return request<{ conversations: ChatConversation[] }>("/api/chat/conversations");
}

export function getConversation(conversationId: string) {
  return request<{ conversation_id: string; messages: ChatMessageData[] }>(
    `/api/chat/${conversationId}`,
  );
}

export function deleteConversation(conversationId: string) {
  return request<{ status: string }>(`/api/chat/${conversationId}`, {
    method: "DELETE",
  });
}

export function getChatSourcePreview(sourcePath: string, sourcePlatform?: string) {
  const params = new URLSearchParams({ source_path: sourcePath });
  if (sourcePlatform) {
    params.set("source_platform", sourcePlatform.toLowerCase());
  }

  return request<{
    source_path: string;
    source_platform: string;
    title: string;
    section_heading?: string;
    content: string;
    score?: number;
  }>(`/api/chat/source-preview/by-path?${params.toString()}`);
}

export function chatStreamUrl() {
  return `${BASE_URL}/api/chat`;
}

// ── SSE stream URL builder ────────────────────────────

export function streamUrl(analysisId: string) {
  return `${BASE_URL}/api/analyze/${analysisId}/stream`;
}
