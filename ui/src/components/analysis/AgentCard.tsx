import {
  Search,
  Brain,
  Route,
  GitBranch,
  AlertTriangle,
  BarChart3,
  Quote,
  Sparkles,
} from "lucide-react";
import type { AgentStepEvent } from "../../lib/schemas";
import type { AgentState } from "../../stores/analysis";

/* ── Agent color mapping ──────────────────────────────── */

export const AGENT_COLORS: Record<
  string,
  { dot: string; text: string; badge: string }
> = {
  plan: {
    dot: "bg-violet-500",
    text: "text-violet-600 dark:text-violet-400",
    badge:
      "bg-violet-100 text-violet-700 border-violet-200/60 dark:bg-violet-900/40 dark:text-violet-300 dark:border-violet-700/40",
  },
  retrieve: {
    dot: "bg-sky-500",
    text: "text-sky-600 dark:text-sky-400",
    badge:
      "bg-sky-100 text-sky-700 border-sky-200/60 dark:bg-sky-900/40 dark:text-sky-300 dark:border-sky-700/40",
  },
  route: {
    dot: "bg-purple-500",
    text: "text-purple-600 dark:text-purple-400",
    badge:
      "bg-purple-100 text-purple-700 border-purple-200/60 dark:bg-purple-900/40 dark:text-purple-300 dark:border-purple-700/40",
  },
  deps: {
    dot: "bg-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    badge:
      "bg-amber-100 text-amber-700 border-amber-200/60 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700/40",
  },
  risk: {
    dot: "bg-rose-500",
    text: "text-rose-600 dark:text-rose-400",
    badge:
      "bg-rose-100 text-rose-700 border-rose-200/60 dark:bg-rose-900/40 dark:text-rose-300 dark:border-rose-700/40",
  },
  coverage: {
    dot: "bg-teal-500",
    text: "text-teal-600 dark:text-teal-400",
    badge:
      "bg-teal-100 text-teal-700 border-teal-200/60 dark:bg-teal-900/40 dark:text-teal-300 dark:border-teal-700/40",
  },
  citation: {
    dot: "bg-cyan-500",
    text: "text-cyan-600 dark:text-cyan-400",
    badge:
      "bg-cyan-100 text-cyan-700 border-cyan-200/60 dark:bg-cyan-900/40 dark:text-cyan-300 dark:border-cyan-700/40",
  },
  synthesize: {
    dot: "bg-indigo-500",
    text: "text-indigo-600 dark:text-indigo-400",
    badge:
      "bg-indigo-100 text-indigo-700 border-indigo-200/60 dark:bg-indigo-900/40 dark:text-indigo-300 dark:border-indigo-700/40",
  },
};

export const DEFAULT_COLOR = {
  dot: "bg-zinc-400",
  text: "text-zinc-500 dark:text-zinc-400",
  badge:
    "bg-zinc-100 text-zinc-600 border-zinc-200/60 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700/40",
};

const AGENT_ICONS: Record<string, typeof Search> = {
  plan: Sparkles,
  retrieve: Search,
  route: Route,
  deps: GitBranch,
  risk: AlertTriangle,
  coverage: BarChart3,
  citation: Quote,
  synthesize: Brain,
};

/* ── Timeline Step (single step in unified timeline) ──── */

interface TimelineStepProps {
  step: AgentStepEvent;
  agentKey: string;
  agentName: string;
  relativeTime: string;
}

export function TimelineStep({
  step,
  agentKey,
  agentName,
  relativeTime,
}: TimelineStepProps) {
  const colors = AGENT_COLORS[agentKey] || DEFAULT_COLOR;

  return (
    <div className="flex items-start gap-3 py-1 relative animate-fade-in-fast">
      <div className="flex-shrink-0 w-5 flex items-center justify-center relative z-10">
        <div
          className={`w-[7px] h-[7px] rounded-full ${colors.dot} ring-2 ring-white dark:ring-[#161618]`}
        />
      </div>

      <div className="flex items-baseline gap-2 min-w-0 flex-1 pb-0.5">
        <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500 w-[52px] flex-shrink-0 text-right tabular-nums">
          {relativeTime}
        </span>
        <span
          className={`text-[11px] font-semibold flex-shrink-0 tracking-tight ${colors.text}`}
        >
          {agentName}
        </span>
        <span
          className={`text-[10px] font-medium px-1.5 py-px rounded-md border flex-shrink-0 ${colors.badge}`}
        >
          {step.action}
        </span>
        {step.detail && (
          <span className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">
            {step.detail}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Agent Status Chip (compact indicator) ────────────── */

interface AgentChipProps {
  agentKey: string;
  agent: AgentState;
}

export function AgentChip({ agentKey, agent }: AgentChipProps) {
  const colors = AGENT_COLORS[agentKey] || DEFAULT_COLOR;
  const Icon = AGENT_ICONS[agentKey] || Brain;
  const isActive =
    agent.status === "searching" ||
    agent.status === "reasoning" ||
    agent.status === "verifying";
  const isComplete = agent.status === "complete";
  const isFailed = agent.status === "failed";

  return (
    <div
      className={`flex items-center gap-1.5 px-2 py-1 rounded-md border transition-colors ${
        isActive
          ? colors.badge
          : isComplete
            ? "bg-zinc-50 border-zinc-200/60 dark:bg-zinc-800/40 dark:border-zinc-700/40"
            : isFailed
              ? "bg-rose-50 border-rose-200/60 dark:bg-rose-900/30 dark:border-rose-700/40"
              : "bg-zinc-50 border-zinc-200/40 dark:bg-zinc-800/20 dark:border-zinc-700/30"
      }`}
    >
      <div className="relative flex-shrink-0">
        <div
          className={`w-1.5 h-1.5 rounded-full ${
            isFailed
              ? "bg-rose-500"
              : isComplete
                ? "bg-emerald-500"
                : isActive
                  ? `${colors.dot} animate-breathing`
                  : "bg-zinc-300 dark:bg-zinc-600"
          }`}
        />
      </div>
      <Icon
        className={`w-3 h-3 ${
          isActive
            ? colors.text
            : isComplete
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-zinc-400 dark:text-zinc-500"
        }`}
      />
      <span
        className={`text-[10px] font-medium ${
          isActive
            ? colors.text
            : isComplete
              ? "text-zinc-600 dark:text-zinc-300"
              : "text-zinc-400 dark:text-zinc-500"
        }`}
      >
        {agent.name}
      </span>
    </div>
  );
}

/* ── AgentCard (per-agent, all steps visible) ─────────── */

interface AgentCardProps {
  agent: AgentState;
  agentKey?: string;
}

export function AgentCard({ agent, agentKey = "" }: AgentCardProps) {
  const colors = AGENT_COLORS[agentKey] || DEFAULT_COLOR;
  const Icon = AGENT_ICONS[agentKey] || Brain;
  const isActive =
    agent.status === "searching" ||
    agent.status === "reasoning" ||
    agent.status === "verifying";

  return (
    <div className="py-2.5">
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            agent.status === "failed"
              ? "bg-rose-500"
              : agent.status === "complete"
                ? "bg-emerald-500"
                : isActive
                  ? `${colors.dot} animate-breathing`
                  : "bg-zinc-300 dark:bg-zinc-600"
          }`}
        />
        <Icon className={`w-3 h-3 ${colors.text}`} />
        <span
          className={`text-[13px] font-medium tracking-tight ${colors.text}`}
        >
          {agent.name}
        </span>
        <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
          {agent.status === "complete"
            ? `${agent.steps.length} steps`
            : agent.status === "failed"
              ? "Failed"
              : isActive
                ? agent.detail
                : "Queued"}
        </span>
      </div>

      {agent.steps.length > 0 && (
        <div className="ml-[18px] pl-3 border-l-2 border-zinc-200 dark:border-zinc-700/50 space-y-1 mt-1.5">
          {agent.steps.map((step, i) => (
            <div key={i} className="flex items-baseline gap-2 text-[11px]">
              <span
                className={`font-medium px-1.5 py-px rounded-md text-[10px] border flex-shrink-0 ${colors.badge}`}
              >
                {step.action}
              </span>
              <span className="text-zinc-500 dark:text-zinc-400 truncate">
                {step.detail}
              </span>
            </div>
          ))}
        </div>
      )}

      {agent.status === "failed" && agent.error && (
        <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-1 ml-[18px]">
          {agent.error}
        </p>
      )}
    </div>
  );
}
