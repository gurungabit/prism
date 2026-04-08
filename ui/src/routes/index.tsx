import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useHealth, useTeams, useConflicts } from "../hooks/useGraph";
import { useHistory } from "../hooks/useAnalysis";
import { useSources } from "../hooks/useSources";
import { Button } from "../components/shared/Button";
import { Badge } from "../components/shared/Badge";
import { Skeleton } from "../components/shared/Skeleton";
import {
  FlaskConical,
  Search,
  MessageCircle,
  AlertTriangle,
  ChevronRight,
} from "lucide-react";

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function DashboardPage() {
  const health = useHealth();
  const teams = useTeams();
  const history = useHistory(5, 0);
  const sources = useSources();
  const conflicts = useConflicts();
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  const teamList = teams.data?.teams ?? [];
  const teamCount = teamList.length;
  const serviceCount = teamList.reduce((sum, t) => sum + (t.services?.length ?? 0), 0);
  const sourceCount = sources.data?.total ?? 0;
  const conflictCount = conflicts.data?.conflicts?.length ?? 0;

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
            Dashboard
          </h1>
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            Overview of your organization's knowledge base.
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          {health.isLoading ? (
            <span className="w-2 h-2 rounded-full bg-zinc-300 dark:bg-zinc-600 animate-breathing" />
          ) : health.data ? (
            <span className="w-2 h-2 rounded-full bg-emerald-500" title="System healthy" />
          ) : (
            <span className="w-2 h-2 rounded-full bg-rose-500" title="Connection error" />
          )}
          <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
            {health.isLoading ? "Checking" : health.data ? "Online" : "Offline"}
          </span>
        </div>
      </div>

      {teams.isLoading ? (
        <div className="flex items-center gap-2">
          <Skeleton className="h-4 w-48" />
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-zinc-400 dark:text-zinc-500">
          <span className="text-zinc-900 dark:text-zinc-100 font-semibold">{teamCount}</span>
          <span>teams</span>
          <span className="text-zinc-300 dark:text-zinc-600">·</span>
          <span className="text-zinc-900 dark:text-zinc-100 font-semibold">{serviceCount}</span>
          <span>services</span>
          <span className="text-zinc-300 dark:text-zinc-600">·</span>
          <span className="text-zinc-900 dark:text-zinc-100 font-semibold">{sourceCount}</span>
          <span>documents</span>
          {conflictCount > 0 && (
            <>
              <span className="text-zinc-300 dark:text-zinc-600">·</span>
              <span className="text-amber-600 dark:text-amber-400 font-semibold">{conflictCount}</span>
              <span className="text-amber-600 dark:text-amber-400">conflicts</span>
            </>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Link to="/analyze">
          <Button size="sm" icon={<FlaskConical className="w-3.5 h-3.5" />}>
            New Analysis
          </Button>
        </Link>
        <Link to="/search">
          <Button variant="secondary" size="sm" icon={<Search className="w-3.5 h-3.5" />}>
            Search
          </Button>
        </Link>
        <Link to="/chat">
          <Button variant="secondary" size="sm" icon={<MessageCircle className="w-3.5 h-3.5" />}>
            Chat
          </Button>
        </Link>
      </div>

      {teams.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : teamList.length > 0 ? (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/30 pt-6">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3">
            Teams
          </h2>
          <div className="space-y-0">
            {teamList.map((team) => (
              <div key={team.team}>
                <button
                  onClick={() => setExpandedTeam(expandedTeam === team.team ? null : team.team)}
                  className={`
                    flex items-center justify-between w-full text-left py-2.5 -mx-2 px-2 rounded-md transition-colors
                    hover:bg-zinc-50 dark:hover:bg-zinc-800/30
                    ${expandedTeam === team.team ? "bg-zinc-50 dark:bg-zinc-800/30" : ""}
                  `}
                >
                  <span className="text-[13px] font-medium text-zinc-700 dark:text-zinc-300">
                    {team.team}
                  </span>
                  <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                    {team.services?.length ?? 0} services
                  </span>
                </button>

                {expandedTeam === team.team && (
                  <div className="pb-2 pl-4 animate-fade-in">
                    {team.description && (
                      <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mb-2">
                        {team.description}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-1">
                      {team.services?.map((svc) => (
                        <Badge key={svc} variant="neutral" size="sm">
                          {svc}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {history.data && history.data.analyses.length > 0 && (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/30 pt-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              Recent Analyses
            </h2>
            <Link
              to="/history"
              className="text-[11px] text-zinc-400 hover:text-[var(--color-accent)] dark:hover:text-[var(--color-accent-dark)] transition-colors"
            >
              View all
            </Link>
          </div>
          <div className="space-y-0">
            {history.data.analyses.map((run) => (
              <Link
                key={run.analysis_id}
                to="/analyze/$runId"
                params={{ runId: run.analysis_id }}
                className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors group"
              >
                <div className="flex-1 min-w-0 mr-3">
                  <p className="text-[12px] text-zinc-700 dark:text-zinc-300 truncate group-hover:text-[var(--color-accent)] dark:group-hover:text-[var(--color-accent-dark)] transition-colors">
                    {run.requirement}
                  </p>
                  <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                    {timeAgo(run.created_at)}
                  </span>
                </div>
                <ChevronRight className="w-3 h-3 text-zinc-300 dark:text-zinc-700 group-hover:text-zinc-400 transition-colors" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {conflictCount > 0 && (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/30 pt-6">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3 flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3 text-amber-500" />
            Ownership Conflicts
          </h2>
          <div className="space-y-0">
            {(conflicts.data?.conflicts as Array<Record<string, unknown>>)?.map((conflict, i) => (
              <div key={i} className="py-2.5 border-b border-zinc-100 dark:border-zinc-800/30 last:border-0">
                <span className="text-[12px] font-mono text-zinc-700 dark:text-zinc-300">
                  {String(conflict.service ?? "")}
                </span>
                {Array.isArray(conflict.claimed_by) && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {(conflict.claimed_by as Array<Record<string, unknown>>).map((c, j) => (
                      <Badge key={j} variant="warning" size="sm">
                        {String(c.team ?? "")}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
