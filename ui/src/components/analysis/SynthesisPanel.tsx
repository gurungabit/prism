import { Streamdown } from "streamdown";
import type { PRISMReport } from "../../lib/schemas";
import type { AgentState } from "../../stores/analysis";
import { Badge } from "../shared/Badge";

interface SynthesisPanelProps {
  report: PRISMReport | null;
  agents: Record<string, AgentState>;
  isConnecting: boolean;
}

function latestStepData(agent?: AgentState): Record<string, unknown> | null {
  if (!agent) return null;
  for (let i = agent.steps.length - 1; i >= 0; i -= 1) {
    const data = agent.steps[i]?.data;
    if (data && typeof data === "object" && !Array.isArray(data)) {
      return data as Record<string, unknown>;
    }
  }
  return null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function SummaryList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-2">
        {title}
      </h3>
      <ul className="space-y-1.5">
        {items.map((item, index) => (
          <li
            key={`${title}-${index}`}
            className="text-[12px] text-zinc-600 dark:text-zinc-300 flex items-start gap-2"
          >
            <span className="w-1 h-1 rounded-full bg-[var(--color-accent)] dark:bg-[var(--color-accent-dark)] mt-[7px] flex-shrink-0" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ContextChip({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  if (!value) return null;
  return (
    <div className="p-3 rounded-lg border border-zinc-200/60 dark:border-zinc-700/40 bg-white/70 dark:bg-zinc-800/30">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-1">
        {label}
      </div>
      <p className="text-[12px] text-zinc-600 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
        {value}
      </p>
    </div>
  );
}

function LiveAgentCards({ agents }: { agents: Record<string, AgentState> }) {
  const cards = [
    {
      key: "retrieve",
      title: "Evidence Search",
      data: latestStepData(agents.retrieve),
      render: (data: Record<string, unknown>) => (
        <>
          <p className="text-[13px] font-medium text-zinc-800 dark:text-zinc-200">
            {String(data.chunks_found ?? data.documents_retrieved ?? "Searching")}
            {" "}documents surfaced
          </p>
          {stringList(data.platforms).length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {stringList(data.platforms).map((platform) => (
                <Badge key={platform} variant="neutral" size="sm">
                  {platform}
                </Badge>
              ))}
            </div>
          )}
        </>
      ),
    },
    {
      key: "route",
      title: "Ownership Signal",
      data: latestStepData(agents.route),
      render: (data: Record<string, unknown>) => (
        <>
          <p className="text-[13px] font-medium text-zinc-800 dark:text-zinc-200">
            {String(data.primary_team ?? "Evaluating team ownership")}
          </p>
          {data.confidence && (
            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1">
              Confidence: {String(data.confidence)}
            </p>
          )}
          <SummaryList title="Services In Scope" items={stringList(data.affected_services).slice(0, 4)} />
        </>
      ),
    },
    {
      key: "deps",
      title: "Dependency Signal",
      data: latestStepData(agents.deps),
      render: (data: Record<string, unknown>) => (
        <>
          <SummaryList title="Blocking Dependencies" items={stringList(data.blocking).slice(0, 4)} />
          <SummaryList title="Non-Blocking Dependencies" items={stringList(data.impacted).slice(0, 4)} />
        </>
      ),
    },
    {
      key: "risk",
      title: "Risk And Effort",
      data: latestStepData(agents.risk),
      render: (data: Record<string, unknown>) => (
        <>
          {(Boolean(data.overall_risk) || Boolean(data.effort_range)) && (
            <div className="flex flex-wrap gap-2 mb-2">
              {Boolean(data.overall_risk) && (
                <Badge variant="warning" size="sm">
                  Risk: {String(data.overall_risk)}
                </Badge>
              )}
              {Boolean(data.effort_range) && (
                <Badge variant="accent" size="sm">
                  Effort: {String(data.effort_range)}
                </Badge>
              )}
            </div>
          )}
          <SummaryList title="Key Risks" items={stringList(data.risks).slice(0, 4)} />
        </>
      ),
    },
    {
      key: "coverage",
      title: "Coverage",
      data: latestStepData(agents.coverage),
      render: (data: Record<string, unknown>) => (
        <>
          {typeof data.needs_retry === "boolean" && (
            <Badge variant={data.needs_retry ? "warning" : "success"} size="sm">
              {data.needs_retry ? "Retry suggested" : "Coverage acceptable"}
            </Badge>
          )}
          <SummaryList title="Critical Gaps" items={stringList(data.critical_gaps).slice(0, 4)} />
          <SummaryList title="Gaps" items={stringList(data.gaps).slice(0, 4)} />
        </>
      ),
    },
  ].filter((card) => card.data);

  if (cards.length === 0) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-4">
      {cards.map((card) => (
        <div
          key={card.key}
          className="p-4 rounded-xl border border-zinc-200/60 dark:border-zinc-700/40 bg-white/80 dark:bg-zinc-900/70"
        >
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-2">
            {card.title}
          </div>
          {card.render(card.data!)}
        </div>
      ))}
    </div>
  );
}

function LiveWorkingBrief({ agents }: { agents: Record<string, AgentState> }) {
  const route = latestStepData(agents.route);
  const risk = latestStepData(agents.risk);
  const coverage = latestStepData(agents.coverage);
  const citation = latestStepData(agents.citation);

  const summaryParts = [
    route?.primary_team ? `Current owner signal points to ${String(route.primary_team)}.` : "",
    stringList(route?.affected_services).length > 0
      ? `Services in scope so far: ${stringList(route?.affected_services).slice(0, 4).join(", ")}.`
      : "",
    risk?.overall_risk ? `Overall risk currently looks ${String(risk.overall_risk)}.` : "",
    risk?.effort_range ? `Estimated effort signal: ${String(risk.effort_range)}.` : "",
    stringList(coverage?.critical_gaps).length > 0
      ? `There are still ${stringList(coverage?.critical_gaps).length} critical documentation gaps.`
      : "",
    stringList(citation?.unsupported_claims).length > 0
      ? `${stringList(citation?.unsupported_claims).length} claims still need stronger evidence.`
      : "",
  ].filter(Boolean);

  return (
    <div className="py-6 border-b border-zinc-200/60 dark:border-zinc-700/30">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3">
        Working Brief
      </h2>
      <div className="border-l-2 border-[var(--color-accent)] dark:border-[var(--color-accent-dark)] pl-4">
        <p className="text-[13px] text-zinc-700 dark:text-zinc-300 leading-[1.7]">
          {summaryParts.length > 0
            ? summaryParts.join(" ")
            : "Agents are building the first pass. Ownership, dependencies, and risks will appear here as soon as each stage returns results."}
        </p>
      </div>
      <LiveAgentCards agents={agents} />
    </div>
  );
}

export function SynthesisPanel({
  report,
  agents,
  isConnecting,
}: SynthesisPanelProps) {
  if (isConnecting) {
    return (
      <div className="py-6">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] dark:bg-[var(--color-accent-dark)] animate-breathing" />
          <p className="text-[13px] text-zinc-400 dark:text-zinc-500">
            Waiting for agents...
          </p>
        </div>
      </div>
    );
  }

  if (!report) {
    return <LiveWorkingBrief agents={agents} />;
  }

  const analysisInput = report.analysis_input;

  return (
    <div className="py-6 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-5">
      <div>
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3">
          Executive Brief
        </h2>
        <div className="border-l-2 border-[var(--color-accent)] dark:border-[var(--color-accent-dark)] pl-4">
          <div className="prose-chat text-[13px] text-zinc-700 dark:text-zinc-300 leading-[1.7]">
            <Streamdown mode="static">
              {report.executive_summary || report.requirement}
            </Streamdown>
          </div>
        </div>
      </div>

      {(report.recommendations.length > 0 || report.caveats.length > 0 || report.data_quality_summary) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 p-4 rounded-xl border border-zinc-200/60 dark:border-zinc-700/40 bg-white/80 dark:bg-zinc-900/70">
            <SummaryList title="Recommendations" items={report.recommendations} />
            {report.caveats.length > 0 && (
              <div className="mt-4">
                <SummaryList title="Caveats" items={report.caveats} />
              </div>
            )}
          </div>
          <div className="p-4 rounded-xl border border-zinc-200/60 dark:border-zinc-700/40 bg-white/80 dark:bg-zinc-900/70">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-2">
              Data Quality
            </div>
            <p className="text-[12px] text-zinc-600 dark:text-zinc-300 leading-relaxed">
              {report.data_quality_summary || "No major data-quality issues were surfaced in the final pass."}
            </p>
          </div>
        </div>
      )}

      {report.impact_matrix.length > 0 && (
        <div className="p-4 rounded-xl border border-zinc-200/60 dark:border-zinc-700/40 bg-white/80 dark:bg-zinc-900/70">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3">
            Cross-Team Snapshot
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {report.impact_matrix.slice(0, 4).map((row, index) => (
              <div
                key={`${row.team}-${row.service}-${index}`}
                className="p-3 rounded-lg border border-zinc-200/60 dark:border-zinc-700/40 bg-zinc-50/70 dark:bg-zinc-800/30"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="accent" size="sm">
                    {row.team}
                  </Badge>
                  <Badge variant="neutral" size="sm">
                    {row.service}
                  </Badge>
                  {row.role && (
                    <Badge variant="info" size="sm">
                      {row.role}
                    </Badge>
                  )}
                </div>
                <p className="text-[12px] text-zinc-600 dark:text-zinc-300 mt-2 leading-relaxed">
                  {row.why_involved}
                </p>
                {row.blocker && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-2">
                    Blocker: {row.blocker}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {analysisInput && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <ContextChip label="Requirement" value={analysisInput.requirement} />
          <ContextChip label="Business Goal" value={analysisInput.business_goal} />
          <ContextChip label="Constraints" value={analysisInput.constraints} />
          <ContextChip label="Additional Context" value={analysisInput.context} />
          <ContextChip label="Known Teams" value={analysisInput.known_teams} />
          <ContextChip label="Known Services" value={analysisInput.known_services} />
        </div>
      )}
    </div>
  );
}
