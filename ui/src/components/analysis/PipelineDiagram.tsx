import { useState, useEffect } from "react";
import type { AgentState } from "../../stores/analysis";
import { PipelineNode } from "./PipelineNode";
import { PipelineEdge } from "./PipelineEdge";
import { PipelineNodeDetail } from "./PipelineNodeDetail";

const PIPELINE_KEYS = [
  "plan",
  "retrieve",
  "route",
  "deps",
  "risk",
  "coverage",
  "citation",
  "synthesize",
] as const;

/* ── Elapsed time computation ──────────────────────── */

function computeElapsed(agent: AgentState | undefined, now: number, effectiveStatus?: string): string {
  if (!agent || agent.steps.length === 0) return "";
  const first = agent.steps[0]!.timestamp;
  const last = agent.steps[agent.steps.length - 1]!.timestamp;
  const isMs = first > 1e12;

  const status = effectiveStatus || agent.status;
  const isActive =
    status === "searching" ||
    status === "reasoning" ||
    status === "verifying";

  const endTs = isActive ? (isMs ? now : now / 1000) : last;
  const delta = isMs ? (endTs - first) / 1000 : endTs - first;
  const sec = Math.max(0, delta);

  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

/* ── Main PipelineDiagram ──────────────────────────── */

interface PipelineDiagramProps {
  agents: Record<string, AgentState>;
  isLive: boolean;
}

export function PipelineDiagram({ agents, isLive }: PipelineDiagramProps) {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  // Tick elapsed timer while live
  useEffect(() => {
    if (!isLive) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isLive]);

  // Track whether user has manually picked a node (disables auto-follow)
  const [userPinned, setUserPinned] = useState(false);

  // Auto-follow: select the currently active agent while live
  useEffect(() => {
    if (!isLive || userPinned) return;
    const active = PIPELINE_KEYS.find((k) => {
      const a = agents[k];
      return a && (a.status === "searching" || a.status === "reasoning" || a.status === "verifying");
    });
    if (active && active !== selectedAgent) {
      setSelectedAgent(active);
    }
  }, [agents, isLive, userPinned, selectedAgent]);

  // Reset pinned state when a new run starts
  useEffect(() => {
    if (!isLive) setUserPinned(false);
  }, [isLive]);

  const handleNodeClick = (key: string) => {
    setUserPinned(true);
    if (selectedAgent === key) {
      setSelectedAgent(null);
    } else if (agents[key]) {
      setSelectedAgent(key);
    }
  };

  // Get the latest step timestamp for an agent
  function lastStepTs(a: AgentState | undefined): number {
    if (!a || a.steps.length === 0) return 0;
    return a.steps[a.steps.length - 1]!.timestamp;
  }

  // Determine effective status for each node, accounting for retry loops.
  // An agent should show "complete" if a LATER agent has MORE RECENT steps.
  // But if the agent's latest step is newer than all later agents (retry loop),
  // keep its raw status so it shows as active.
  function getEffectiveStatus(idx: number): string {
    const agent = agents[PIPELINE_KEYS[idx]!];
    if (!agent) return "queued";
    const raw = agent.status;
    if (raw === "complete" || raw === "failed") return raw;

    const myTs = lastStepTs(agent);
    // Check if any later agent has a more recent step
    for (let j = idx + 1; j < PIPELINE_KEYS.length; j++) {
      const later = agents[PIPELINE_KEYS[j]!];
      if (later && later.steps.length > 0 && lastStepTs(later) > myTs) {
        return "complete"; // Later agent ran after us → we're done
      }
    }
    return raw; // No later agent is newer → keep our actual status
  }

  const selectedAgentState = selectedAgent ? agents[selectedAgent] : undefined;

  return (
    <div className="py-4 border-b border-zinc-200/50 dark:border-zinc-700/20">
      {/* Pipeline row */}
      <div className="flex items-center gap-0 overflow-x-auto pt-3 pb-4 px-2 pipeline-scroll">
        {PIPELINE_KEYS.map((key, i) => {
          const agent = agents[key];
          const effectiveStatus = getEffectiveStatus(i);
          const elapsed = computeElapsed(agent, now, effectiveStatus);

          const prevEffective = i > 0 ? getEffectiveStatus(i - 1) : undefined;

          return (
            <div key={key} className="flex items-center flex-shrink-0">
              {/* Edge before node (except first) */}
              {i > 0 && (
                <PipelineEdge
                  fromStatus={prevEffective}
                  toStatus={effectiveStatus}
                />
              )}
              {/* Node */}
              <div>
                <PipelineNode
                  agentKey={key}
                  agent={agent}
                  isSelected={selectedAgent === key}
                  onClick={() => handleNodeClick(key)}
                  elapsedTime={elapsed}
                  effectiveStatus={effectiveStatus}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Detail panel */}
      {selectedAgent && selectedAgentState && (
        <PipelineNodeDetail
          agentKey={selectedAgent}
          agent={selectedAgentState}
          elapsedTime={computeElapsed(selectedAgentState, now)}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}
