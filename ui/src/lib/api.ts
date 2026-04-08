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
}

export function startAnalysis(input: AnalysisInput) {
  return request<{ analysis_id: string; stream_url: string }>(
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

// ── Ingestion ─────────────────────────────────────────

export function triggerIngest(force = false) {
  return request<{ status: string; message: string }>(
    `/api/ingest?force=${force}`,
    { method: "POST" },
  );
}

export function triggerPlatformIngest(platform: string, force = false) {
  return request<{ status: string; platform: string }>(
    `/api/ingest/${platform}?force=${force}`,
    { method: "POST" },
  );
}

export function triggerFullIngest() {
  return request<{ status: string; message: string }>(
    "/api/ingest/full",
    { method: "POST" },
  );
}

// ── Search ────────────────────────────────────────────

export interface SearchParams {
  query: string;
  filters?: Record<string, unknown>;
  page?: number;
  page_size?: number;
  top_k?: number;
}

export interface SearchResult {
  chunk_id: string;
  content: string;
  score: number;
  source_path: string;
  document_title: string;
  doc_type: string;
  platform: string;
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

export function getConflicts() {
  return request<{ conflicts: unknown[] }>("/api/graph/conflicts");
}

// ── Health ────────────────────────────────────────────

export function healthCheck() {
  return request<{ status: string; service: string }>("/api/health");
}

// ── History ───────────────────────────────────────────

export interface HistoryEntry {
  analysis_id: string;
  requirement: string;
  status: string;
  created_at: string;
  duration_seconds: number | null;
}

export function getHistory(limit = 20, offset = 0) {
  return request<{ analyses: HistoryEntry[]; total: number }>(
    `/api/history?limit=${limit}&offset=${offset}`,
  );
}

export function deleteAnalysis(analysisId: string) {
  return request<{ status: string; analysis_id: string }>(
    `/api/history/${analysisId}`,
    { method: "DELETE" },
  );
}

// ── Sources listing ──────────────────────────────────

export interface SourceDocument {
  document_id: string;
  source_path: string;
  chunk_count: number;
  status: string;
  last_ingested_at: string | null;
}

export interface SourceGroup {
  platform: string;
  document_count: number;
  last_ingested: string | null;
  documents: SourceDocument[];
}

export function getSourcesList() {
  return request<{ sources: SourceGroup[]; total: number }>("/api/sources");
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
