import { Check, X } from "lucide-react";
import type { AgentState } from "../../stores/analysis";
import { AGENT_COLORS, DEFAULT_COLOR } from "./AgentCard";
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

const AGENT_LABELS: Record<string, string> = {
  plan: "Plan",
  retrieve: "Retrieve",
  route: "Route",
  deps: "Deps",
  risk: "Risk",
  coverage: "Coverage",
  citation: "Citation",
  synthesize: "Synthesize",
};

/* CSS variable color values for the glow animation */
const GLOW_COLORS: Record<string, string> = {
  plan: "rgba(139, 92, 246, 0.3)",
  retrieve: "rgba(14, 165, 233, 0.3)",
  route: "rgba(168, 85, 247, 0.3)",
  deps: "rgba(245, 158, 11, 0.3)",
  risk: "rgba(244, 63, 94, 0.3)",
  coverage: "rgba(20, 184, 166, 0.3)",
  citation: "rgba(6, 182, 212, 0.3)",
  synthesize: "rgba(99, 102, 241, 0.3)",
};

interface PipelineNodeProps {
  agentKey: string;
  agent: AgentState | undefined;
  isSelected: boolean;
  onClick: () => void;
  elapsedTime: string;
  effectiveStatus?: string;
}

export function PipelineNode({
  agentKey,
  agent,
  isSelected,
  onClick,
  elapsedTime,
  effectiveStatus,
}: PipelineNodeProps) {
  const colors = AGENT_COLORS[agentKey] || DEFAULT_COLOR;
  const Icon = AGENT_ICONS[agentKey] || Brain;
  const label = AGENT_LABELS[agentKey] || agentKey;

  const status = effectiveStatus || agent?.status;
  const isActive =
    status === "searching" ||
    status === "reasoning" ||
    status === "verifying";
  const isComplete = status === "complete";
  const isFailed = status === "failed";
  const isQueued = !agent || status === "queued";

  const statusDot = (isComplete || isFailed || isActive) ? (
    <div className="absolute -top-1.5 -right-1.5 z-20 pointer-events-none">
      {isComplete && (
        <div className="w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center shadow-sm ring-2 ring-[#161618] dark:ring-[#161618]">
          <Check className="w-2.5 h-2.5 text-white" strokeWidth={3} />
        </div>
      )}
      {isFailed && (
        <div className="w-4 h-4 rounded-full bg-rose-500 flex items-center justify-center shadow-sm ring-2 ring-[#161618] dark:ring-[#161618]">
          <X className="w-2.5 h-2.5 text-white" strokeWidth={3} />
        </div>
      )}
      {isActive && (
        <div className={`w-3.5 h-3.5 rounded-full ${colors.dot} animate-breathing shadow-sm ring-2 ring-[#161618] dark:ring-[#161618]`} />
      )}
    </div>
  ) : null;

  return (
    <div className="relative">
      {statusDot}
      <button
        type="button"
        onClick={onClick}
        className={`
          relative flex flex-col items-center gap-1 px-2.5 py-2 rounded-xl border
          transition-all duration-300 min-w-[68px] max-w-[88px] group cursor-pointer
          ${isSelected ? "ring-2 ring-offset-1 ring-zinc-400/40 dark:ring-zinc-500/40 dark:ring-offset-[#161618]" : ""}
          ${
            isActive
              ? `${colors.badge} animate-node-glow border-current`
              : isComplete
                ? "bg-emerald-50/50 border-emerald-200/60 dark:bg-emerald-950/20 dark:border-emerald-700/40"
                : isFailed
                  ? "bg-rose-50/50 border-rose-200/60 dark:bg-rose-950/20 dark:border-rose-700/40"
                  : "bg-zinc-50/50 border-zinc-200/40 dark:bg-zinc-800/20 dark:border-zinc-700/30 opacity-50"
          }
          ${!isQueued ? "hover:scale-[1.04]" : "hover:opacity-70"}
        `}
        style={
          isActive
            ? ({ "--node-glow-color": GLOW_COLORS[agentKey] || "rgba(99, 102, 241, 0.25)" } as React.CSSProperties)
            : undefined
        }
      >
      {/* Icon */}
      <Icon
        className={`w-4 h-4 ${
          isActive
            ? colors.text
            : isComplete
              ? "text-emerald-600 dark:text-emerald-400"
              : isFailed
                ? "text-rose-500"
                : "text-zinc-400 dark:text-zinc-500"
        }`}
      />

      {/* Label */}
      <span
        className={`text-[10px] font-semibold tracking-tight leading-none ${
          isActive
            ? colors.text
            : isComplete
              ? "text-emerald-700 dark:text-emerald-300"
              : isFailed
                ? "text-rose-600 dark:text-rose-400"
                : "text-zinc-400 dark:text-zinc-500"
        }`}
      >
        {label}
      </span>

      {/* Elapsed time */}
      {elapsedTime && (
        <span className="text-[9px] font-mono text-zinc-400 dark:text-zinc-500 leading-none">
          {elapsedTime}
        </span>
      )}

      {/* Active detail text */}
      {isActive && agent?.detail && (
        <span className="text-[8px] text-zinc-500 dark:text-zinc-400 leading-tight text-center max-w-full truncate mt-0.5">
          {agent.detail}
        </span>
      )}

      </button>

      {/* Selection indicator — outside button to avoid clipping */}
      {isSelected && !isQueued && (
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[5px] border-r-[5px] border-t-[5px] border-transparent border-t-zinc-300 dark:border-t-zinc-600 pointer-events-none" />
      )}
    </div>
  );
}
