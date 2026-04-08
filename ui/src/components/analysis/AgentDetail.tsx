import type { AgentState } from "../../stores/analysis";
import { Badge } from "../shared/Badge";

interface AgentDetailProps {
  agent: AgentState;
  onClose: () => void;
}

export function AgentDetail({ agent, onClose }: AgentDetailProps) {
  return (
    <div className="py-4 border-b border-zinc-200/60 dark:border-zinc-700/30 animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[14px] font-semibold text-zinc-800 dark:text-zinc-200 tracking-tight">
          {agent.name}
        </h3>
        <button
          onClick={onClose}
          className="text-[11px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
        >
          Close
        </button>
      </div>

      {agent.steps.length > 0 && (
        <div className="space-y-1.5 border-l-2 border-zinc-200 dark:border-zinc-700/50 pl-3">
          {agent.steps.map((step, i) => (
            <div key={i} className="text-[11px]">
              <div className="flex items-center gap-2">
                <Badge variant="neutral" size="sm">
                  {step.action}
                </Badge>
                <span className="text-zinc-400 dark:text-zinc-500 truncate">
                  {step.detail}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {agent.status === "failed" && agent.error && (
        <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-2">
          {agent.error}
        </p>
      )}
    </div>
  );
}
