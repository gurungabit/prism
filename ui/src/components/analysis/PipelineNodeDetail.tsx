import { X, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { AgentState } from "../../stores/analysis";
import { AGENT_COLORS, DEFAULT_COLOR } from "./AgentCard";
import { Badge } from "../shared/Badge";

interface PipelineNodeDetailProps {
  agentKey: string;
  agent: AgentState;
  elapsedTime: string;
  onClose: () => void;
}

/* ── Rich data renderer for agent step output ──────── */

function StepData({
  data,
}: {
  data: Record<string, unknown>;
}) {
  const [expandReasoning, setExpandReasoning] = useState(false);

  const LABEL_OVERRIDES: Record<string, string> = {
    affected_services: "services in scope",
    impacted: "non-blocking dependencies",
    blocking: "blocking dependencies",
    informational_count: "contextual dependency count",
    primary_team: "recommended owner",
  };

  const reasoning = typeof data.reasoning === "string" && data.reasoning.length > 0 ? data.reasoning : null;
  const entries = Object.entries(data).filter(([k]) => k !== "reasoning");

  return (
    <div className="ml-[50px] mt-1.5 mb-2 space-y-1.5">
      {/* Key-value and list items */}
      {entries.map(([key, value]) => {
        const label = LABEL_OVERRIDES[key] ?? key.replace(/_/g, " ");

        // Arrays render as bullet lists
        if (Array.isArray(value) && value.length > 0) {
          return (
            <div key={key}>
              <span className="text-[10px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
                {label}
              </span>
              <ul className="mt-0.5 space-y-0.5">
                {(value as string[]).map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-1.5 text-[11px] text-zinc-600 dark:text-zinc-300"
                  >
                    <span className="w-1 h-1 rounded-full bg-zinc-400 dark:bg-zinc-500 mt-[5px] flex-shrink-0" />
                    <span className="font-mono text-[10px] leading-relaxed">{String(item)}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        }

        // Booleans render as badges
        if (typeof value === "boolean") {
          return (
            <div key={key} className="flex items-center gap-1.5">
              <span className="text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
                {label}:
              </span>
              <span
                className={`text-[10px] font-medium px-1.5 py-px rounded-md ${
                  value
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                    : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                }`}
              >
                {value ? "yes" : "no"}
              </span>
            </div>
          );
        }

        // Scalars render inline
        if (value != null && !Array.isArray(value) && typeof value !== "object") {
          return (
            <span
              key={key}
              className="inline-flex items-center gap-1 mr-3 text-[10px] text-zinc-400 dark:text-zinc-500"
            >
              <span className="font-medium text-zinc-500 dark:text-zinc-400">
                {label}:
              </span>
              <span className="font-mono text-zinc-600 dark:text-zinc-300">
                {String(value)}
              </span>
            </span>
          );
        }

        return null;
      })}

      {/* Reasoning block - collapsible */}
      {reasoning && (
        <div className="mt-1">
          <button
            type="button"
            onClick={() => setExpandReasoning(!expandReasoning)}
            className="flex items-center gap-1 text-[10px] font-medium text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
          >
            <ChevronRight
              className={`w-3 h-3 transition-transform ${expandReasoning ? "rotate-90" : ""}`}
            />
            AI Reasoning
          </button>
          {expandReasoning && (
            <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed pl-4 border-l-2 border-zinc-200 dark:border-zinc-700/50 italic animate-fade-in">
              {reasoning}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function PipelineNodeDetail({
  agentKey,
  agent,
  elapsedTime,
  onClose,
}: PipelineNodeDetailProps) {
  const colors = AGENT_COLORS[agentKey] || DEFAULT_COLOR;

  const isActive =
    agent.status === "searching" ||
    agent.status === "reasoning" ||
    agent.status === "verifying";

  // Use the agent's own first step as the base so timestamps are agent-relative
  const agentFirstTs = agent.steps.length > 0 ? agent.steps[0]!.timestamp : 0;
  const tsIsMs = agentFirstTs > 1e12;

  function fmtRel(ts: number): string {
    const sec = Math.max(0, tsIsMs ? (ts - agentFirstTs) / 1000 : ts - agentFirstTs);
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }

  return (
    <div className="animate-slide-up border border-zinc-200/60 dark:border-zinc-700/40 rounded-xl bg-white/80 dark:bg-zinc-900/80 backdrop-blur-sm p-4 mt-4 max-h-[420px] overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            agent.status === "failed"
              ? "bg-rose-500"
              : agent.status === "complete"
                ? "bg-emerald-500"
                : isActive
                  ? `${colors.dot} animate-breathing`
                  : "bg-zinc-300 dark:bg-zinc-600"
          }`} />
          <span className={`text-[13px] font-semibold tracking-tight ${colors.text}`}>
            {agent.name}
          </span>
          <Badge
            variant={
              agent.status === "complete"
                ? "success"
                : agent.status === "failed"
                  ? "danger"
                  : isActive
                    ? "accent"
                    : "neutral"
            }
            size="sm"
          >
            {agent.status}
          </Badge>
          {elapsedTime && (
            <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500">
              {elapsedTime}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Steps */}
      {agent.steps.length > 0 && (
        <div className="space-y-1.5 border-l-2 border-zinc-200 dark:border-zinc-700/50 pl-3">
          {agent.steps.map((step, i) => (
            <div key={step.id || i}>
              <div className="flex items-baseline gap-2 text-[11px]">
                <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500 w-[52px] flex-shrink-0 text-right tabular-nums">
                  {fmtRel(step.timestamp)}
                </span>
                <span className={`font-medium px-1.5 py-px rounded-md text-[10px] border flex-shrink-0 ${colors.badge}`}>
                  {step.action}
                </span>
                {step.detail && (
                  <span className="text-zinc-500 dark:text-zinc-400">
                    {step.detail}
                  </span>
                )}
              </div>

              {/* Structured data */}
              {step.data != null && typeof step.data === "object" && (
                <StepData data={step.data as Record<string, unknown>} />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {agent.status === "failed" && agent.error && (
        <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-2 ml-[50px]">
          {agent.error}
        </p>
      )}

      {agent.steps.length === 0 && (
        <p className="text-[11px] text-zinc-400 dark:text-zinc-500 italic">
          Waiting for events...
        </p>
      )}
    </div>
  );
}
