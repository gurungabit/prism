import { create } from "zustand";
import type { PRISMReport, AgentStepEvent } from "../lib/schemas";
import type { StreamStatus } from "../lib/stream";

export type AgentStatus =
  | "queued"
  | "searching"
  | "reasoning"
  | "verifying"
  | "complete"
  | "failed";

export interface AgentState {
  name: string;
  status: AgentStatus;
  detail: string;
  steps: AgentStepEvent[];
  error?: string;
}

interface AnalysisState {
  runId: string | null;
  streamStatus: StreamStatus | "idle";
  agents: Record<string, AgentState>;
  report: PRISMReport | null;
  error: string | null;

  startRun: (runId: string) => void;
  addAgentStep: (step: AgentStepEvent) => void;
  setReport: (report: PRISMReport) => void;
  setError: (error: string) => void;
  setStreamStatus: (status: StreamStatus) => void;
  reset: () => void;
}

const AGENT_LABELS: Record<string, string> = {
  plan: "Planner",
  retrieve: "Retrieval",
  route: "Router",
  deps: "Dependencies",
  risk: "Risk & Effort",
  coverage: "Coverage",
  citation: "Citation",
  synthesize: "Synthesis",
};

/* Normalize legacy backend keys to the canonical short keys */
const AGENT_KEY_NORMALIZE: Record<string, string> = {
  retrieval: "retrieve",
  router: "route",
  dependency: "deps",
  risk_effort: "risk",
};

function normalizeAgentKey(agent: string, action: string): string {
  if (agent === "orchestrator") {
    return action.includes("synthes") ? "synthesize" : "plan";
  }
  return AGENT_KEY_NORMALIZE[agent] || agent;
}

function mapActionToStatus(action: string): AgentStatus {
  if (action.includes("complete") || action.includes("done")) return "complete";
  if (action.includes("fail") || action.includes("error")) return "failed";
  if (action === "results") return "reasoning";
  if (action.includes("search") || action.includes("retriev")) return "searching";
  if (
    action.includes("reason") ||
    action.includes("analyz") ||
    action.includes("generat") ||
    action.includes("synthes") ||
    action.includes("score") ||
    action.includes("query") ||
    action.includes("travers") ||
    action.includes("check")
  ) return "reasoning";
  if (action.includes("verif")) return "verifying";
  return "searching";
}

const initialState = {
  runId: null as string | null,
  streamStatus: "idle" as StreamStatus | "idle",
  agents: {} as Record<string, AgentState>,
  report: null as PRISMReport | null,
  error: null as string | null,
};

export const useAnalysisStore = create<AnalysisState>((set) => ({
  ...initialState,

  startRun: (runId) =>
    set({
      ...initialState,
      runId,
      streamStatus: "connecting",
    }),

  addAgentStep: (step) =>
    set((s) => {
      const key = normalizeAgentKey(step.agent, step.action);
      const label = AGENT_LABELS[key] || key;
      const existing = s.agents[key];
      const status = mapActionToStatus(step.action);

      return {
        agents: {
          ...s.agents,
          [key]: {
            name: label,
            status,
            detail: step.detail || step.action,
            steps: [...(existing?.steps || []), step],
            ...(status === "failed" ? { error: step.detail } : {}),
          },
        },
      };
    }),

  setReport: (report) =>
    set({ report }),

  setError: (error) => set({ error }),

  setStreamStatus: (status) => set({ streamStatus: status }),

  reset: () => set(initialState),
}));
