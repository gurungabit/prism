import { useState, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams, Link } from "@tanstack/react-router";
import { useThread, useStartAnalysis } from "../hooks/useAnalysis";
import {
  CheckCircle2,
  FlaskConical,
  Loader2,
} from "lucide-react";
import type { ThreadTurn } from "../lib/api";
import { ChatInput } from "../components/chat/ChatInput";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import { TimelineStep } from "../components/analysis/AgentCard";
import { PipelineDiagram } from "../components/analysis/PipelineDiagram";
import { SynthesisPanel } from "../components/analysis/SynthesisPanel";
import { FindingCard } from "../components/analysis/FindingCard";
import {
  Badge,
  RiskBadge,
  ImpactBadge,
  ConfidenceBadge,
} from "../components/shared/Badge";
import type { PRISMReport } from "../lib/schemas";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  ExternalLink,
  WifiOff,
  Clock,
  FileText,
  Users,
  Gauge,
  Shield,
  Layers,
  GitBranch,
  FileDown,
} from "lucide-react";
import { Button } from "../components/shared/Button";

function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
}

type Citation = NonNullable<
  PRISMReport["team_routing"]
>["primary_team"]["sources"][number];
type SourceDoc = PRISMReport["all_sources"][number];
type DepEdge = PRISMReport["dependencies"]["blocking"][number];
type ImpactMatrixRow = PRISMReport["impact_matrix"][number];

// Turn inline path references (e.g. "necrokings/RetryOps@main:README.md")
// inside a narrative string into clickable links when we have a URL for them.
// We match on the raw path strings from ``report.all_sources`` rather than
// parsing the "[Doc N]" prefix, because the LLM sometimes emits just the path,
// sometimes the bracket + path, and sometimes a bare [Doc N] alone. Matching
// paths directly handles all three cleanly.
function linkifyNarrative(
  text: string,
  urlByPath: Record<string, string>,
): ReactNode[] {
  const paths = Object.keys(urlByPath)
    .filter((p) => urlByPath[p])
    .sort((a, b) => b.length - a.length);
  if (paths.length === 0 || !text) return [text];

  const escaped = paths.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "g");

  const out: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    const path = match[1];
    if (!path) continue;
    if (match.index > lastIndex) out.push(text.slice(lastIndex, match.index));
    out.push(
      <a
        key={`link-${key++}`}
        href={urlByPath[path]}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-baseline gap-0.5 font-mono text-[11px] text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline break-all"
      >
        {path}
      </a>,
    );
    lastIndex = match.index + path.length;
  }
  if (lastIndex < text.length) out.push(text.slice(lastIndex));
  return out;
}

function Narrative({
  text,
  urlByPath,
  className,
}: {
  text: string;
  urlByPath: Record<string, string>;
  className?: string;
}) {
  return (
    <p
      className={
        className ??
        "text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed"
      }
    >
      {linkifyNarrative(text, urlByPath)}
    </p>
  );
}

function InlineSources({ sources }: { sources: Citation[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {sources.map((s, i) => {
        const label = (
          <>
            <FileText className="w-3 h-3 text-zinc-400 dark:text-zinc-500 mt-0.5 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <span
                className={`text-[11px] font-mono break-all leading-relaxed ${
                  s.source_url
                    ? "text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] group-hover:underline"
                    : "text-zinc-500 dark:text-zinc-400"
                }`}
              >
                {s.document_path}
              </span>
              {s.excerpt && (
                <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5 italic leading-relaxed">
                  &ldquo;{s.excerpt}&rdquo;
                </p>
              )}
            </div>
          </>
        );

        return s.source_url ? (
          <a
            key={i}
            href={s.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-start gap-1.5 group"
          >
            {label}
          </a>
        ) : (
          <div key={i} className="flex items-start gap-1.5">
            {label}
          </div>
        );
      })}
    </div>
  );
}

function DependencyGroup({
  label,
  edges,
}: {
  label: string;
  edges: DepEdge[];
}) {
  if (edges.length === 0) return null;
  return (
    <div className="mb-5 last:mb-0">
      <div className="flex items-center gap-2 mb-2">
        <ImpactBadge impact={label.toLowerCase()} />
        <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
          ({edges.length})
        </span>
      </div>
      <div className="space-y-3 ml-1">
        {edges.map((edge, i) => (
          <div
            key={i}
            className="pl-3 border-l-2 border-zinc-200 dark:border-zinc-700/50"
          >
            <div className="flex items-center gap-1.5 text-[13px]">
              <span className="font-mono text-zinc-700 dark:text-zinc-300">
                {edge.from_service}
              </span>
              <ArrowRight className="w-3 h-3 text-zinc-400 dark:text-zinc-500" />
              <span className="font-mono text-zinc-700 dark:text-zinc-300">
                {edge.to_service}
              </span>
            </div>
            {edge.reason && (
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5 italic">
                &ldquo;{edge.reason}&rdquo;
              </p>
            )}
            <InlineSources sources={edge.sources} />
          </div>
        ))}
      </div>
    </div>
  );
}

function SourceCard({ source }: { source: SourceDoc }) {
  const classes = `p-3 rounded-lg border transition-colors ${
    source.is_stale
      ? "border-amber-200/60 bg-amber-50/30 dark:border-amber-700/30 dark:bg-amber-950/10"
      : "border-zinc-200/60 bg-white dark:border-zinc-700/40 dark:bg-zinc-800/30"
  } ${source.source_url ? "hover:border-[var(--color-accent)]/50 dark:hover:border-[var(--color-accent-dark)]/50 cursor-pointer" : ""}`;

  const body = (
    <>
      <div className="flex items-start gap-2">
        {source.is_stale && (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
        )}
        <span
          className={`text-[12px] font-mono break-all leading-snug ${
            source.source_url
              ? "text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]"
              : "text-zinc-700 dark:text-zinc-300"
          }`}
          title={source.path}
        >
          {source.path}
        </span>
        {source.source_url && (
          <ExternalLink className="w-3 h-3 text-zinc-400 dark:text-zinc-500 mt-1 flex-shrink-0" />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <Badge variant="neutral" size="sm">
          {source.platform}
        </Badge>
        <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500">
          Score: {source.relevance_score.toFixed(2)}
        </span>
        {source.is_stale && (
          <span className="text-[10px] font-medium text-amber-600 dark:text-amber-400">
            Stale
          </span>
        )}
        {source.last_modified && (
          <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
            {source.last_modified}
          </span>
        )}
      </div>
      {source.sections_cited.length > 0 && (
        <div className="mt-2 text-[10px] text-zinc-400 dark:text-zinc-500">
          <span className="font-medium">Cited:</span>{" "}
          {source.sections_cited.map((sec, i) => (
            <span key={i}>
              &ldquo;{sec}&rdquo;
              {i < source.sections_cited.length - 1 && ", "}
            </span>
          ))}
        </div>
      )}
    </>
  );

  return source.source_url ? (
    <a
      href={source.source_url}
      target="_blank"
      rel="noopener noreferrer"
      className={`block ${classes}`}
    >
      {body}
    </a>
  ) : (
    <div className={classes}>{body}</div>
  );
}

function impactConfidenceVariant(
  confidence: ImpactMatrixRow["confidence"],
): "success" | "warning" | "danger" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "danger";
}

function CollapsibleSection({
  title,
  icon,
  children,
  defaultOpen = false,
  count,
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="py-4 border-b border-zinc-200/50 dark:border-zinc-700/20">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`
          inline-flex items-center gap-1.5 -mx-2 px-2 py-1.5 rounded-lg
          transition-colors duration-150 group
          hover:bg-zinc-100/70 dark:hover:bg-zinc-800/40
        `}
      >
        <span className={`
          text-zinc-300 dark:text-zinc-600
          group-hover:text-zinc-500 dark:group-hover:text-zinc-400
          transition-all duration-150
          ${open ? "rotate-90" : "rotate-0"}
        `}>
          <ChevronRight className="w-3.5 h-3.5" />
        </span>
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 flex items-center gap-1.5 group-hover:text-zinc-600 dark:group-hover:text-zinc-300 transition-colors">
          {icon}
          {title}
          {count !== undefined && (
            <span className="text-zinc-300 dark:text-zinc-600 font-normal">({count})</span>
          )}
        </h2>
      </button>
      {open && (
        <div className="mt-4 animate-fade-in">
          {children}
        </div>
      )}
    </div>
  );
}

function EventLogSection({
  allSteps,
  isLive,
  fmtRel,
  timelineEndRef,
}: {
  allSteps: { step: { id?: string; timestamp: number; action: string; detail?: string }; agentKey: string; agentName: string }[];
  isLive: boolean;
  fmtRel: (ts: number) => string;
  timelineEndRef: React.RefObject<HTMLDivElement>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="py-4 border-b border-zinc-200/50 dark:border-zinc-700/20">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`
          inline-flex items-center gap-1.5 -mx-2 px-2 py-1.5 rounded-lg
          transition-colors duration-150 group
          hover:bg-zinc-100/70 dark:hover:bg-zinc-800/40
        `}
      >
        <span className={`
          text-zinc-300 dark:text-zinc-600
          group-hover:text-zinc-500 dark:group-hover:text-zinc-400
          transition-all duration-150
          ${open ? "rotate-90" : "rotate-0"}
        `}>
          <ChevronRight className="w-3.5 h-3.5" />
        </span>
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 flex items-center gap-1.5 group-hover:text-zinc-600 dark:group-hover:text-zinc-300 transition-colors">
          <Clock className="w-3 h-3" />
          Event Log
          <span className="text-zinc-300 dark:text-zinc-600 font-normal">({allSteps.length})</span>
        </h2>
      </button>

      {open && allSteps.length > 0 && (
        <div className={`relative ml-2 mt-4 animate-fade-in ${isLive ? "analysis-timeline-scroll" : ""}`}>
          <div className="absolute left-[9px] top-2 bottom-2 w-px bg-zinc-200 dark:bg-zinc-700" />
          <div className="relative">
            {allSteps.map(({ step, agentKey, agentName }, i) => (
              <TimelineStep
                key={step.id || i}
                step={step as any}
                agentKey={agentKey}
                agentName={agentName}
                relativeTime={fmtRel(step.timestamp)}
              />
            ))}
            <div ref={timelineEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}

// SingleRunPanel renders one run's live/completed state -- the existing
// monolithic view. The thread route component above it decides when to
// mount this (for the active turn) vs. a compact card for prior turns.
//
// When ``embedded`` is true (the normal thread-view path), we drop the
// standalone hero (back arrow + big requirement heading) because the
// surrounding ThreadTurnCard already shows that context. Only the status
// strip + PDF button remain.
export function SingleRunPanel({
  runId,
  embedded = true,
}: {
  runId: string;
  embedded?: boolean;
}) {
  const stream = useAnalysisStream();
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  useEffect(() => {
    if (runId && stream.runId !== runId) {
      stream.connect(runId);
    }
    return () => stream.disconnect();
  }, [runId]);

  const report = stream.report;
  const agents = stream.agents;
  const isLive =
    stream.streamStatus === "connected" ||
    stream.streamStatus === "connecting";
  const isReconnecting = stream.streamStatus === "reconnecting";
  const isComplete = stream.streamStatus === "closed" && report !== null;
  const requirementText =
    report?.analysis_input?.requirement || report?.requirement || "Analysis";

  const allSteps = useMemo(() => {
    const steps: {
      step: (typeof agents)[string]["steps"][number];
      agentKey: string;
      agentName: string;
    }[] = [];
    for (const [key, agent] of Object.entries(agents)) {
      for (const step of agent.steps) {
        steps.push({ step, agentKey: key, agentName: agent.name });
      }
    }
    steps.sort((a, b) => a.step.timestamp - b.step.timestamp);
    return steps;
  }, [agents]);

  const firstTs = allSteps[0]?.step.timestamp ?? 0;
  const tsIsMs = firstTs > 1e12;

  function fmtRel(ts: number): string {
    const sec = Math.max(0, tsIsMs ? (ts - firstTs) / 1000 : ts - firstTs);
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }

  useEffect(() => {
    if (isLive && timelineEndRef.current) {
      timelineEndRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [allSteps.length, isLive]);

  const teamsCount = report?.team_routing
    ? 1 + (report.team_routing.supporting_teams?.length || 0)
    : 0;
  const servicesCount = report?.affected_services?.length || 0;
  const docsCited = report?.coverage_report?.documents_cited || 0;
  const docsRetrieved = report?.coverage_report?.documents_retrieved || 0;

  const deps = report?.dependencies;
  const hasAnyDeps =
    deps &&
    ((deps.blocking?.length || 0) > 0 ||
      (deps.impacted?.length || 0) > 0 ||
      (deps.informational?.length || 0) > 0);

  // One map of every known doc path -> its web URL. The narrative linkifier
  // uses this to turn inline path references into anchor tags without
  // requiring structured citations from the LLM.
  const urlByPath = useMemo<Record<string, string>>(() => {
    if (!report) return {};
    const map: Record<string, string> = {};
    for (const s of report.all_sources) {
      if (s.source_url) map[s.path] = s.source_url;
    }
    return map;
  }, [report]);

  async function handleDownloadPdf() {
    if (!report) return;

    setPdfError(null);
    setIsExportingPdf(true);

    try {
      const { downloadAnalysisReportPdf } = await import("../lib/reportPdf");
      await downloadAnalysisReportPdf(report);
    } catch (error) {
      console.error("pdf_export_failed", error);
      setPdfError("Could not generate the PDF report. Please try again.");
    } finally {
      setIsExportingPdf(false);
    }
  }

  return (
    <div
      className={
        embedded
          ? "px-6 py-4 space-y-0"
          : "max-w-[1200px] mx-auto px-6 py-6 space-y-0"
      }
    >
      {/* ═══ HEADER BAR ══════════════════════════════════ */}
      {!embedded && (
        <div className="pb-5 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-4">
          <div className="flex items-start gap-3 min-w-0">
            <Link
              to="/analyze"
              className="mt-1 p-1.5 rounded-lg text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-700/30 transition-colors flex-shrink-0"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-400 dark:text-zinc-500">
                Requirement
              </p>
              <h1 className="max-w-[980px] text-[21px] sm:text-[25px] font-semibold tracking-tight leading-[1.18] text-zinc-900 dark:text-zinc-100 whitespace-normal break-words">
                {requirementText}
              </h1>
            </div>
          </div>
        </div>
      )}

      {/* Status + PDF strip. Rendered in both modes, but compact when
          embedded since the surrounding card already carries the title. */}
      <div
        className={
          embedded
            ? "flex flex-wrap items-center gap-2 gap-y-2 pb-3"
            : "flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between pt-4 pb-4 border-b border-zinc-200/60 dark:border-zinc-700/30"
        }
      >
        <div className="flex flex-wrap items-center gap-2 gap-y-2 flex-1 min-w-0">
          <span className="text-[11px] font-mono text-zinc-400 dark:text-zinc-500 truncate">
            {runId}
          </span>
          {isLive && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200/60 dark:border-emerald-700/40">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-breathing" />
              <span className="text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                Live
              </span>
            </div>
          )}
          {isReconnecting && (
            <Badge variant="warning" size="sm">
              <WifiOff className="w-2.5 h-2.5 mr-1" />
              Reconnecting
            </Badge>
          )}
          {stream.streamStatus === "error" && (
            <Badge variant="danger" size="sm">
              <WifiOff className="w-2.5 h-2.5 mr-1" />
              Disconnected
            </Badge>
          )}
          {isComplete && report && (
            <Badge variant="success" size="sm">
              Complete
            </Badge>
          )}
          {report?.duration_seconds ? (
            <span className="text-[11px] font-mono text-zinc-400 dark:text-zinc-500">
              {fmtDuration(report.duration_seconds)}
            </span>
          ) : null}
        </div>

        {isComplete && report && (
          <Button
            variant={embedded ? "secondary" : "accent"}
            size="sm"
            loading={isExportingPdf}
            icon={<FileDown />}
            onClick={handleDownloadPdf}
          >
            {embedded ? "PDF" : "Download PDF"}
          </Button>
        )}
      </div>

      {pdfError && (
        <div className="py-3 border-b border-rose-200/40 dark:border-rose-700/30">
          <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-[13px]">{pdfError}</span>
          </div>
        </div>
      )}

      {/* ═══ METRICS STRIP ═══════════════════════════════ */}
      {report && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 py-4 border-b border-zinc-200/60 dark:border-zinc-700/30 animate-fade-in">
          {report.risk_assessment?.overall_risk && (
            <div className="flex items-center gap-2">
              <Shield className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                Risk
              </span>
              <RiskBadge level={report.risk_assessment.overall_risk} />
            </div>
          )}
          {report.effort_estimate && (
            <div className="flex items-center gap-2">
              <Gauge className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                Effort
              </span>
              <span className="text-[12px] font-mono font-medium text-zinc-700 dark:text-zinc-300">
                {report.effort_estimate.total_days_min}&ndash;
                {report.effort_estimate.total_days_max} days
              </span>
            </div>
          )}
          {teamsCount > 0 && (
            <div className="flex items-center gap-2">
              <Users className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                Teams
              </span>
              <span className="text-[12px] font-mono font-medium text-zinc-700 dark:text-zinc-300">
                {teamsCount}
              </span>
            </div>
          )}
          {servicesCount > 0 && (
            <div className="flex items-center gap-2">
              <Layers className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                Services
              </span>
              <span className="text-[12px] font-mono font-medium text-zinc-700 dark:text-zinc-300">
                {servicesCount}
              </span>
            </div>
          )}
          {(docsCited > 0 || docsRetrieved > 0) && (
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                Docs
              </span>
              <span className="text-[12px] font-mono font-medium text-zinc-700 dark:text-zinc-300">
                {docsCited} cited / {docsRetrieved} retrieved
              </span>
            </div>
          )}
          {report.duration_seconds > 0 && (
            <div className="flex items-center gap-2 ml-auto">
              <Clock className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
              <span className="text-[12px] font-mono text-zinc-500 dark:text-zinc-400">
                {fmtDuration(report.duration_seconds)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* ═══ PIPELINE DIAGRAM ═══════════════════════════ */}
      {(allSteps.length > 0 || Object.keys(agents).length > 0) && (
        <>
          <PipelineDiagram agents={agents} isLive={isLive} />
          <EventLogSection
            allSteps={allSteps}
            isLive={isLive}
            fmtRel={fmtRel}
            timelineEndRef={timelineEndRef}
          />
        </>
      )}

      {/* ═══ SYNTHESIS ═══════════════════════════════════ */}
      <SynthesisPanel
        report={report}
        agents={agents}
        isConnecting={
          stream.streamStatus === "connecting" &&
          Object.keys(agents).length === 0
        }
      />

      {/* ═══ REPORT SECTIONS ═════════════════════════════ */}
      {report && (
        <div className="space-y-0">
          {/* ─── Team Routing ────────────────────────────── */}
          {report.team_routing && (
            <CollapsibleSection title="Team Routing" icon={<Users className="w-3 h-3" />} defaultOpen={true} count={teamsCount}>
              <div className="space-y-4">
                {report.team_routing_narrative && (
                  <Narrative
                    text={report.team_routing_narrative}
                    urlByPath={urlByPath}
                  />
                )}
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[13px] font-medium text-zinc-800 dark:text-zinc-200">
                      {report.team_routing.primary_team.name}
                    </span>
                    <Badge variant="accent" size="sm">
                      primary
                    </Badge>
                    <ConfidenceBadge
                      score={report.team_routing.primary_team.confidence}
                    />
                  </div>
                  <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                    {report.team_routing.primary_team.justification}
                  </p>
                  {report.team_routing.primary_team.role &&
                    report.team_routing.primary_team.role !== "primary" && (
                      <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5">
                        Role: {report.team_routing.primary_team.role}
                      </p>
                    )}
                  <InlineSources
                    sources={report.team_routing.primary_team.sources}
                  />
                </div>

                {report.team_routing.supporting_teams.map((team, i) => (
                  <div
                    key={i}
                    className="pt-4 border-t border-zinc-100 dark:border-zinc-700/40"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[13px] font-medium text-zinc-800 dark:text-zinc-200">
                        {team.name}
                      </span>
                      <Badge variant="neutral" size="sm">
                        {team.role}
                      </Badge>
                      <ConfidenceBadge score={team.confidence} />
                    </div>
                    <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                      {team.justification}
                    </p>
                    <InlineSources sources={team.sources} />
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}

          {/* ─── In-Scope Services ───────────────────────── */}
          {report.affected_services.length > 0 && (
            <CollapsibleSection title="Services In Scope" icon={<Layers className="w-3 h-3" />} defaultOpen={false} count={servicesCount}>
              <p className="text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed mb-3">
                These are the services most likely touched by the requirement itself.
              </p>
              <div className="space-y-0">
                {report.affected_services.map((svc, i) => (
                  <div
                    key={i}
                    className="py-3 border-b border-zinc-100 dark:border-zinc-800/30 last:border-0"
                  >
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-[13px] text-zinc-800 dark:text-zinc-200 font-mono">
                        {svc.name}
                      </span>
                      <ImpactBadge impact={svc.impact} />
                      {svc.owning_team && (
                        <Badge variant="neutral" size="sm">
                          {svc.owning_team}
                        </Badge>
                      )}
                    </div>
                    {svc.changes_needed && (
                      <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                        {svc.changes_needed}
                      </p>
                    )}
                    <InlineSources sources={svc.sources} />
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}

          {report.impact_matrix.length > 0 && (
            <CollapsibleSection title="Cross-Team Impact Matrix" icon={<Layers className="w-3 h-3" />} defaultOpen={true} count={report.impact_matrix.length}>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-zinc-200 dark:border-zinc-700/50">
                      <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                        Team
                      </th>
                      <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                        Service
                      </th>
                      <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                        Role
                      </th>
                      <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                        Confidence
                      </th>
                      <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                        Why Involved
                      </th>
                      <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                        Blocker
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.impact_matrix.map((row, index) => (
                      <tr
                        key={`${row.team}-${row.service}-${row.role}-${index}`}
                        className="align-top border-b border-zinc-100 dark:border-zinc-700/40 last:border-0"
                      >
                        <td className="py-3 pr-4">
                          <Badge variant="accent" size="sm">
                            {row.team}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4">
                          <span className="font-mono text-zinc-700 dark:text-zinc-300">
                            {row.service}
                          </span>
                        </td>
                        <td className="py-3 pr-4">
                          {row.role ? (
                            <Badge variant="info" size="sm">
                              {row.role}
                            </Badge>
                          ) : (
                            <span className="text-zinc-400 dark:text-zinc-500">-</span>
                          )}
                        </td>
                        <td className="py-3 pr-4">
                          <Badge
                            variant={impactConfidenceVariant(row.confidence)}
                            size="sm"
                          >
                            {row.confidence}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4 text-zinc-600 dark:text-zinc-400 leading-relaxed">
                          <div>
                            {row.why_involved
                              ? linkifyNarrative(row.why_involved, urlByPath)
                              : "-"}
                          </div>
                          {row.evidence.length > 0 && (
                            <div className="mt-1 text-[10px] flex flex-wrap gap-x-2 gap-y-1">
                              {row.evidence.slice(0, 4).map((ev, i) =>
                                urlByPath[ev] ? (
                                  <a
                                    key={i}
                                    href={urlByPath[ev]}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="font-mono text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline break-all"
                                  >
                                    {ev}
                                  </a>
                                ) : (
                                  <span
                                    key={i}
                                    className="font-mono text-zinc-400 dark:text-zinc-500 break-all"
                                  >
                                    {ev}
                                  </span>
                                ),
                              )}
                            </div>
                          )}
                        </td>
                        <td className="py-3 text-zinc-600 dark:text-zinc-400 leading-relaxed">
                          {row.blocker ? linkifyNarrative(row.blocker, urlByPath) : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CollapsibleSection>
          )}

          {/* ─── Dependencies ────────────────────────────── */}
          {hasAnyDeps && deps && (
            <CollapsibleSection title="Dependencies" icon={<GitBranch className="w-3 h-3" />} defaultOpen={false} count={(deps.blocking?.length || 0) + (deps.impacted?.length || 0) + (deps.informational?.length || 0)}>
              <p className="text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed mb-3">
                These are service-to-service relationships around the in-scope services.
              </p>
              {report.dependency_narrative && (
                <Narrative
                  text={report.dependency_narrative}
                  urlByPath={urlByPath}
                  className="text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed mb-4"
                />
              )}
              <DependencyGroup
                label="Blocking Dependencies"
                edges={deps.blocking || []}
              />
              <DependencyGroup
                label="Non-Blocking Dependencies"
                edges={deps.impacted || []}
              />
              <DependencyGroup
                label="Contextual Dependencies"
                edges={deps.informational || []}
              />
            </CollapsibleSection>
          )}

          {/* ─── Risk Assessment ─────────────────────────── */}
          {report.risk_assessment &&
            report.risk_assessment.risks.length > 0 && (
              <CollapsibleSection title="Risk Assessment" icon={<Shield className="w-3 h-3" />} defaultOpen={true} count={report.risk_assessment.risks.length}>
                {report.risk_narrative && (
                  <Narrative
                    text={report.risk_narrative}
                    urlByPath={urlByPath}
                    className="text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed mb-3"
                  />
                )}
                <div>
                  {report.risk_assessment.risks.map((risk, i) => (
                    <FindingCard key={i} finding={risk} />
                  ))}
                </div>
              </CollapsibleSection>
            )}

          {/* ─── Effort Breakdown + Staffing ──────────────── */}
          {report.effort_estimate &&
            report.effort_estimate.breakdown.length > 0 && (
              <CollapsibleSection title="Effort Breakdown" icon={<Gauge className="w-3 h-3" />} defaultOpen={false}>
                {report.effort_narrative && (
                  <Narrative
                    text={report.effort_narrative}
                    urlByPath={urlByPath}
                    className="text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed mb-4"
                  />
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-[12px]">
                    <thead>
                      <tr className="border-b border-zinc-200 dark:border-zinc-700/50">
                        <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                          Task
                        </th>
                        <th className="text-left py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                          Team
                        </th>
                        <th className="text-right py-2 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                          Days
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.effort_estimate.breakdown.map((item, i) => (
                        <tr
                          key={i}
                          className="border-b border-zinc-100 dark:border-zinc-700/40 last:border-0"
                        >
                          <td className="py-2 text-zinc-700 dark:text-zinc-300">
                            {item.task}
                          </td>
                          <td className="py-2">
                            <Badge variant="neutral" size="sm">
                              {item.team}
                            </Badge>
                          </td>
                          <td className="py-2 text-right font-mono text-zinc-500 dark:text-zinc-400">
                            {item.days_min}&ndash;{item.days_max}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {report.effort_estimate.staffing && (
                  <div className="mt-6 pt-4 border-t border-zinc-100 dark:border-zinc-700/40">
                    <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3">
                      Staffing
                    </h3>
                    <div className="flex flex-wrap gap-x-8 gap-y-3">
                      <div>
                        <span className="text-[10px] text-zinc-400 dark:text-zinc-500 block">
                          Engineers
                        </span>
                        <span className="text-[14px] font-mono font-semibold text-zinc-800 dark:text-zinc-200">
                          {
                            report.effort_estimate.staffing
                              .engineers_needed
                          }
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-zinc-400 dark:text-zinc-500 block">
                          Reviewers
                        </span>
                        <span className="text-[14px] font-mono font-semibold text-zinc-800 dark:text-zinc-200">
                          {
                            report.effort_estimate.staffing
                              .reviewers_needed
                          }
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-zinc-400 dark:text-zinc-500 block">
                          Calendar
                        </span>
                        <span className="text-[14px] font-mono font-semibold text-zinc-800 dark:text-zinc-200">
                          {
                            report.effort_estimate.staffing
                              .estimated_calendar_weeks_min
                          }
                          &ndash;
                          {
                            report.effort_estimate.staffing
                              .estimated_calendar_weeks_max
                          }{" "}
                          weeks
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {report.effort_estimate.sources.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-zinc-100 dark:border-zinc-700/40">
                    <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-2">
                      Effort Sources
                    </h3>
                    <InlineSources
                      sources={report.effort_estimate.sources}
                    />
                  </div>
                )}
              </CollapsibleSection>
            )}

          {/* ─── Ownership Conflicts ─────────────────────── */}
          {report.conflicts_detected.length > 0 && (
            <CollapsibleSection title="Ownership Conflicts" icon={<AlertTriangle className="w-3 h-3 text-amber-500" />} defaultOpen={false} count={report.conflicts_detected.length}>
              <div className="space-y-3">
                {report.conflicts_detected.map((conflict, i) => {
                  const teams = conflict.claimed_by.map((c) => c.team);
                  const uniqueTeams = [...new Set(teams.map((t) => t.toLowerCase()))];
                  const isNamingIssue = uniqueTeams.length < teams.length;

                  return (
                    <div
                      key={i}
                      className="p-4 rounded-lg border border-amber-200/50 bg-amber-50/20 dark:border-amber-700/20 dark:bg-amber-950/10"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                        <span className="text-[13px] font-mono font-medium text-zinc-800 dark:text-zinc-200">
                          {conflict.service}
                        </span>
                      </div>

                      <p className="text-[12px] text-zinc-600 dark:text-zinc-400 mb-3">
                        {isNamingIssue
                          ? `Multiple references found for the same team under different names: ${teams.join(", ")}`
                          : `Claimed by ${teams.join(" and ")} — needs ownership clarification`}
                      </p>

                      <div className="space-y-2 mb-3">
                        {conflict.claimed_by.map((c, j) => (
                          <div key={j} className="flex items-start gap-2 text-[11px]">
                            <Badge
                              variant={c.confidence === "explicit" ? "warning" : "neutral"}
                              size="sm"
                            >
                              {c.confidence}
                            </Badge>
                            <div className="min-w-0">
                              <span className="font-medium text-zinc-700 dark:text-zinc-300">
                                {c.team}
                              </span>
                              <span className="text-zinc-400 dark:text-zinc-500"> — </span>
                              <span className="font-mono text-zinc-400 dark:text-zinc-500 break-all">
                                {c.source}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>

                      {conflict.resolution && (
                        <div className="pt-2 border-t border-amber-200/30 dark:border-amber-700/20">
                          <p className="text-[11px] text-zinc-600 dark:text-zinc-400">
                            <span className="font-medium text-zinc-700 dark:text-zinc-300">Recommendation: </span>
                            {conflict.resolution}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CollapsibleSection>
          )}

          {(report.verification_report.verified_claims.length > 0 ||
            report.verification_report.unsupported_claims.length > 0 ||
            report.coverage_report.critical_gaps.length > 0 ||
            report.coverage_report.stale_sources.length > 0) && (
            <CollapsibleSection title="Verification & Gaps" icon={<FileText className="w-3 h-3" />} defaultOpen={false}>
              {report.data_quality_summary && (
                <p className="text-[12px] text-zinc-600 dark:text-zinc-400 leading-relaxed mb-4">
                  {report.data_quality_summary}
                </p>
              )}

              {report.verification_report.verified_claims.length > 0 && (
                <div className="mb-5">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-2">
                    Verified Claims
                  </h3>
                  <div className="space-y-2">
                    {report.verification_report.verified_claims.slice(0, 8).map((claim, index) => (
                      <div
                        key={`${claim.claim}-${index}`}
                        className="p-3 rounded-lg border border-zinc-200/60 dark:border-zinc-700/40 bg-white dark:bg-zinc-800/20"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="success" size="sm">
                            {claim.confidence}
                          </Badge>
                          {urlByPath[claim.supporting_doc] ? (
                            <a
                              href={urlByPath[claim.supporting_doc]}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[11px] font-mono text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline break-all inline-flex items-center gap-1"
                            >
                              {claim.supporting_doc}
                              <ExternalLink className="w-3 h-3 flex-shrink-0" />
                            </a>
                          ) : (
                            <span className="text-[11px] font-mono text-zinc-400 dark:text-zinc-500 break-all">
                              {claim.supporting_doc}
                            </span>
                          )}
                        </div>
                        <p className="text-[12px] text-zinc-700 dark:text-zinc-300">
                          {claim.claim}
                        </p>
                        {claim.excerpt && (
                          <p className="text-[11px] text-zinc-500 dark:text-zinc-400 italic mt-1">
                            &ldquo;{claim.excerpt}&rdquo;
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {report.verification_report.unsupported_claims.length > 0 && (
                <div className="mb-5">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-2">
                    Unsupported Claims
                  </h3>
                  <ul className="space-y-1.5">
                    {report.verification_report.unsupported_claims.map((claim, index) => (
                      <li
                        key={`${claim}-${index}`}
                        className="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-start gap-2"
                      >
                        <span className="w-1 h-1 rounded-full bg-amber-400 dark:bg-amber-500 mt-[5px] flex-shrink-0" />
                        {claim}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {report.coverage_report.critical_gaps.length > 0 && (
                <div className="mb-5">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-2">
                    Critical Gaps
                  </h3>
                  <ul className="space-y-1.5">
                    {report.coverage_report.critical_gaps.map((gap, index) => (
                      <li
                        key={`${gap}-${index}`}
                        className="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-start gap-2"
                      >
                        <span className="w-1 h-1 rounded-full bg-amber-400 dark:bg-amber-500 mt-[5px] flex-shrink-0" />
                        {gap}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {report.coverage_report.stale_sources.length > 0 && (
                <div>
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-2">
                    Stale Sources
                  </h3>
                  <ul className="space-y-1.5">
                    {report.coverage_report.stale_sources.slice(0, 6).map((source, index) => (
                      <li
                        key={`${source}-${index}`}
                        className="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-start gap-2"
                      >
                        <span className="w-1 h-1 rounded-full bg-zinc-400 dark:bg-zinc-500 mt-[5px] flex-shrink-0" />
                        {source}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CollapsibleSection>
          )}
        </div>
      )}

      {/* ═══ SOURCES & COVERAGE ══════════════════════════ */}
      {report &&
        (report.all_sources.length > 0 || report.coverage_report) && (
          <CollapsibleSection title="Sources & Coverage" icon={<FileText className="w-3 h-3" />} defaultOpen={false} count={report.all_sources.length}>
            {report.coverage_report && (
              <div className="flex flex-wrap items-center gap-3 mb-5 py-3 px-4 rounded-lg bg-zinc-50 dark:bg-zinc-800/30 border border-zinc-200/60 dark:border-zinc-700/40">
                <span className="text-[12px] font-mono text-zinc-700 dark:text-zinc-300">
                  {report.coverage_report.documents_retrieved} docs
                  retrieved
                </span>
                <span className="text-zinc-300 dark:text-zinc-600">
                  &middot;
                </span>
                <span className="text-[12px] font-mono text-zinc-700 dark:text-zinc-300">
                  {report.coverage_report.documents_cited} cited
                </span>
                <span className="text-zinc-300 dark:text-zinc-600">
                  &middot;
                </span>
                <span className="text-[12px] font-mono text-zinc-700 dark:text-zinc-300">
                  {report.coverage_report.retrieval_rounds} retrieval
                  rounds
                </span>
                {report.coverage_report.platforms_searched.length > 0 && (
                  <>
                    <span className="text-zinc-300 dark:text-zinc-600">
                      &middot;
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {report.coverage_report.platforms_searched.map(
                        (p) => (
                          <Badge key={p} variant="neutral" size="sm">
                            {p}
                          </Badge>
                        ),
                      )}
                    </div>
                  </>
                )}
              </div>
            )}

            {report.all_sources.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-5">
                {report.all_sources.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            )}

            {report.coverage_report &&
              report.coverage_report.gaps.length > 0 && (
                <div className="mt-4 pt-3 border-t border-zinc-100 dark:border-zinc-700/40">
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-2 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    Data Gaps
                  </h3>
                  <ul className="space-y-1.5">
                    {report.coverage_report.gaps.map((gap, i) => (
                      <li
                        key={i}
                        className="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-start gap-2"
                      >
                        <span className="w-1 h-1 rounded-full bg-amber-400 dark:bg-amber-500 mt-[5px] flex-shrink-0" />
                        {gap}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
          </CollapsibleSection>
        )}

      {/* ═══ ERROR STATE ═════════════════════════════════ */}
      {stream.error && !report && (
        <div className="py-4">
          <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-[13px]">{stream.error}</span>
          </div>
        </div>
      )}
    </div>
  );
}


// ═══ THREAD PAGE ═════════════════════════════════════════════════════════
// The route component. The URL segment is interpreted as a thread id (or any
// run id within a thread -- we resolve either way). For single-turn threads
// this degenerates to the old single-run page. For multi-turn threads it
// renders the prior turns as stacked cards above the active run.

export function AnalyzeRunPage() {
  const { runId: urlId } = useParams({ strict: false }) as { runId: string };
  const navigate = useNavigate();

  // Refetch every 3s while anything is running -- the backend writes the
  // new turn's row as soon as /api/analyze returns, and the planner +
  // streaming events trail; polling keeps the thread view in sync without
  // threading SSE through every turn.
  const thread = useThread(urlId, 3000);
  const turns = thread.data?.turns ?? [];
  const threadId = thread.data?.thread_id ?? urlId;

  // Redirect the URL to the canonical thread id the first time we resolve
  // a non-root run_id. Keeps browser history / bookmarks stable.
  useEffect(() => {
    if (thread.data && thread.data.thread_id !== urlId) {
      navigate({
        to: "/analyze/$runId",
        params: { runId: thread.data.thread_id },
        replace: true,
      });
    }
  }, [thread.data?.thread_id, urlId, navigate]);

  const startAnalysis = useStartAnalysis();

  const hasRunning = turns.some((t) => t.status === "running");
  const activeTurn = [...turns].reverse().find((t) => t.status === "running") ?? turns[turns.length - 1];

  async function submitFollowUp(text: string, forceFull: boolean) {
    if (!activeTurn) return;
    const result = await startAnalysis.mutateAsync({
      requirement: text,
      parent_analysis_id: activeTurn.analysis_id,
      force_full: forceFull,
    });
    // URL stays on the thread; the new turn appears when the polling
    // query refetches. Kick a manual refetch to shorten the delay.
    await thread.refetch();
    return result;
  }

  if (thread.isLoading) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-8 space-y-4">
        <div className="h-5 w-48 bg-zinc-100 dark:bg-zinc-800/50 rounded animate-pulse" />
        <div className="h-32 w-full bg-zinc-100 dark:bg-zinc-800/50 rounded-lg animate-pulse" />
      </div>
    );
  }

  if (thread.isError || turns.length === 0) {
    return (
      <div className="max-w-[720px] mx-auto px-6 py-16">
        <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
          <AlertTriangle className="w-4 h-4" />
          <span className="text-[13px]">
            {thread.error instanceof Error ? thread.error.message : "Thread not found"}
          </span>
        </div>
      </div>
    );
  }

  const rootRequirement = turns[0]?.requirement ?? "Analysis";

  return (
    // Flex-column that fills the main scroll area. The body scrolls
    // internally; the follow-up input is a flex-end child so it stays
    // pinned at the viewport bottom regardless of content length.
    <div className="flex flex-col h-full max-w-[1200px] mx-auto">
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
      {/* Thread header -- one root requirement, N turns */}
      <div className="pb-4 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-2">
        <div className="flex items-start gap-3 min-w-0">
          <Link
            to="/analyze"
            className="mt-1 p-1.5 rounded-lg text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-700/30 transition-colors flex-shrink-0"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-400 dark:text-zinc-500">
              Thread
            </p>
            <h1 className="text-[18px] sm:text-[21px] font-semibold tracking-tight leading-[1.2] text-zinc-900 dark:text-zinc-100 whitespace-normal break-words">
              {rootRequirement}
            </h1>
            <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-1.5 font-mono">
              {threadId} · {turns.length} {turns.length === 1 ? "turn" : "turns"}
            </p>
          </div>
        </div>
      </div>

      {/* Stacked turns, oldest first. The latest turn is expanded by default;
          if there's a running turn, it also gets rendered live. */}
      <div className="space-y-3">
        {turns.map((turn, i) => {
          const isLatest = i === turns.length - 1;
          return (
            <ThreadTurnCard
              key={turn.analysis_id}
              turn={turn}
              turnIndex={i + 1}
              totalTurns={turns.length}
              defaultOpen={isLatest}
              // The first turn's requirement is already shown as the thread
              // title; showing it again as a bubble would be a duplicate.
              // Every follow-up turn gets a bubble so the page reads like a
              // conversation.
              showUserBubble={i > 0}
              onRunFullAnalysis={
                turn.kind === "chat" && turn.status === "complete"
                  ? async () => {
                      await submitFollowUp(turn.requirement, true);
                    }
                  : undefined
              }
            />
          );
        })}
      </div>
      </div>

      {/* Input pinned at bottom of the flex column. ChatInput matches the
          /chat page's affordance so users get consistent muscle memory. */}
      <ChatInput
        disabled={hasRunning || startAnalysis.isPending}
        placeholder={
          hasRunning
            ? "Waiting for previous turn..."
            : "Ask a follow-up. I'll answer from prior context, or run a full analysis if needed."
        }
        onSend={(text) => {
          void submitFollowUp(text, false);
        }}
      />
    </div>
  );
}


// ── ThreadTurnCard ─────────────────────────────────────────────────────────
// A single turn inside a thread. Renders as a collapsible card. Chat turns
// render as message bubbles; full turns embed SingleRunPanel (live or
// completed) when expanded.

interface ThreadTurnCardProps {
  turn: ThreadTurn;
  turnIndex: number;
  totalTurns: number;
  defaultOpen: boolean;
  showUserBubble: boolean;
  onRunFullAnalysis?: () => void | Promise<void>;
}

function ThreadTurnCard({
  turn,
  turnIndex,
  totalTurns,
  defaultOpen,
  onRunFullAnalysis,
  showUserBubble,
}: ThreadTurnCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  // Every turn gets a user-bubble for its requirement -- chat turns had
  // this already, full turns used to bury it in the card title. Surfacing
  // it here makes the thread read like a conversation regardless of mode.
  const bubble = showUserBubble && (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-zinc-100 dark:bg-zinc-700/40 rounded-2xl rounded-br-md px-4 py-2.5 text-[13px] text-zinc-800 dark:text-zinc-200 leading-relaxed whitespace-pre-wrap">
        {turn.requirement}
      </div>
    </div>
  );

  // Pending: planner hasn't decided yet. Show a lightweight "thinking..."
  // indicator for follow-ups so the full pipeline doesn't flash before
  // the planner resolves. For the first turn we already know the answer
  // must be "full" (planner forces it), so we skip the pending state and
  // jump straight to the pipeline view.
  if (turn.kind === "pending" && turnIndex > 1) {
    return (
      <div className="space-y-3">
        {bubble}
        <PendingTurnIndicator />
      </div>
    );
  }

  if (turn.kind === "chat") {
    return (
      <div className="space-y-3">
        {bubble}
        <ChatTurnCard turn={turn} onRunFullAnalysis={onRunFullAnalysis} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {bubble}
      <FullTurnCard
        turn={turn}
        turnIndex={turnIndex}
        totalTurns={totalTurns}
        open={open}
        onToggle={() => setOpen(!open)}
      />
    </div>
  );
}

function PendingTurnIndicator() {
  return (
    <div className="flex items-center gap-2 text-[13px] text-zinc-500 dark:text-zinc-400">
      <Loader2 className="w-3.5 h-3.5 animate-spin" />
      Thinking...
    </div>
  );
}

function ChatTurnCard({
  turn,
  onRunFullAnalysis,
}: {
  turn: ThreadTurn;
  onRunFullAnalysis?: () => void | Promise<void>;
}) {
  const answer = turn.report?.chat_answer?.answer ?? "";
  const citedPaths = turn.report?.chat_answer?.cited_paths ?? [];
  const isRunning = turn.status === "running";
  const [triggering, setTriggering] = useState(false);

  // User bubble is rendered by ThreadTurnCard; here we just show the
  // assistant response as prose.
  return (
    <div className="space-y-3">
      {isRunning ? (
        <div className="flex items-center gap-2 text-[13px] text-zinc-500 dark:text-zinc-400">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Answering from prior context...
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-[13px] text-zinc-700 dark:text-zinc-300 leading-[1.7] whitespace-pre-wrap">
            {answer || "(no answer)"}
          </p>

          {citedPaths.length > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
              {citedPaths.slice(0, 5).map((p, i) => (
                <span
                  key={i}
                  className="font-mono text-zinc-400 dark:text-zinc-500 break-all"
                >
                  {p}
                </span>
              ))}
            </div>
          )}

          {onRunFullAnalysis && (
            <div>
              <Button
                variant="secondary"
                size="sm"
                loading={triggering}
                icon={<FlaskConical className="w-3 h-3" />}
                onClick={async () => {
                  setTriggering(true);
                  try {
                    await onRunFullAnalysis();
                  } finally {
                    setTriggering(false);
                  }
                }}
              >
                Run full analysis
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FullTurnCard({
  turn,
  turnIndex,
  totalTurns,
  open,
  onToggle,
}: {
  turn: ThreadTurn;
  turnIndex: number;
  totalTurns: number;
  open: boolean;
  onToggle: () => void;
}) {
  const isRunning = turn.status === "running";
  const isComplete = turn.status === "complete";

  // Prefer the exec summary; fall back to the rolling summary if synthesis
  // didn't populate one (e.g. mid-run).
  const previewText = useMemo(() => {
    const exec = (turn.report as any)?.executive_summary;
    if (typeof exec === "string" && exec.trim()) return exec;
    if (turn.rolling_summary) return turn.rolling_summary;
    return isRunning ? "Analysis running..." : "(no summary)";
  }, [turn, isRunning]);

  return (
    <div className="rounded-lg border border-zinc-200/70 dark:border-zinc-700/40 bg-white dark:bg-[#1e1e20] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors"
      >
        <ChevronRight
          className={`w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500 mt-1 flex-shrink-0 transition-transform ${
            open ? "rotate-90" : ""
          }`}
        />
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2 text-[11px]">
            <span className="font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              Turn {turnIndex} of {totalTurns} · full
            </span>
            {isRunning && (
              <Badge variant="info" size="sm">
                <Loader2 className="w-2.5 h-2.5 mr-1 animate-spin" />
                Running
              </Badge>
            )}
            {isComplete && (
              <Badge variant="success" size="sm">
                <CheckCircle2 className="w-2.5 h-2.5 mr-1" />
                Complete
              </Badge>
            )}
          </div>
          <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 truncate">
            {turn.requirement}
          </div>
          {!open && (
            <p className="text-[12px] text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed">
              {previewText}
            </p>
          )}
        </div>
      </button>

      {open && (
        <div className="border-t border-zinc-200/70 dark:border-zinc-700/40">
          {isRunning || isComplete ? (
            // Reuse the single-run panel. It handles both live streaming and
            // the completed report read-back based on /api/analyze/<id>/report.
            <SingleRunPanel runId={turn.analysis_id} />
          ) : (
            <div className="px-6 py-6 text-[12px] text-zinc-500 dark:text-zinc-400">
              This run didn't complete successfully. Status: {turn.status}.
            </div>
          )}
        </div>
      )}
    </div>
  );
}


