import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Building2,
  ChevronRight,
  FlaskConical,
  MessageCircle,
  Plug,
  Search,
  Sparkles,
  Users,
} from "lucide-react";

import { useHealth, useTeams } from "../hooks/useGraph";
import { useHistory } from "../hooks/useAnalysis";
import { useCreateOrg, useDeclaredSources, useOrgs } from "../hooks/useCatalog";
import { Button } from "../components/shared/Button";
import { Input } from "../components/shared/Input";
import { Badge } from "../components/shared/Badge";
import { EmptyState } from "../components/shared/EmptyState";
import { Skeleton } from "../components/shared/Skeleton";

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
  const sources = useDeclaredSources();
  const orgs = useOrgs();
  const createOrg = useCreateOrg();
  const navigate = useNavigate();

  const [orgName, setOrgName] = useState("");
  const [orgFormError, setOrgFormError] = useState<string | null>(null);

  const teamList = teams.data?.teams ?? [];
  const teamCount = teamList.length;
  const serviceCount = teamList.reduce((sum, t) => sum + (t.services?.length ?? 0), 0);
  const sourceCount = sources.data?.total ?? 0;
  const primaryOrg = orgs.data?.orgs[0];

  // Wait for the orgs query before deciding between the create-org empty
  // state and the dashboard. Rendering the dashboard during loading causes a
  // flash when the query resolves to "no org" and we swap to the create form.
  if (orgs.isLoading) {
    return (
      <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-64" />
        </div>
        <Skeleton className="h-14 w-full" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-28" />
        </div>
      </div>
    );
  }

  // No org yet: show an inline create-org form. This used to bounce the user
  // to a dedicated /setup page, but the only actionable step there was naming
  // the org, so it lives here now.
  if (!primaryOrg) {
    return (
      <div className="max-w-[560px] mx-auto px-6 py-16 space-y-8">
        <div className="flex items-center gap-3">
          <Sparkles className="w-5 h-5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
            Welcome to PRISM
          </h1>
        </div>
        <p className="text-[13px] leading-relaxed text-zinc-500 dark:text-zinc-400">
          Start by naming your organization. Teams, services, and data sources
          all hang off of it. You can add more later.
        </p>

        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            setOrgFormError(null);
            if (!orgName.trim()) {
              setOrgFormError("Organization name is required");
              return;
            }
            try {
              const created = await createOrg.mutateAsync(orgName.trim());
              navigate({ to: "/orgs/$orgId", params: { orgId: created.id } });
            } catch (err) {
              setOrgFormError(
                err instanceof Error ? err.message : "Failed to create organization",
              );
            }
          }}
        >
          <Input
            label="Organization name"
            placeholder="e.g. Acme Engineering"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            error={orgFormError ?? undefined}
            autoFocus
          />
          <Button
            type="submit"
            icon={<Building2 className="w-3.5 h-3.5" />}
            loading={createOrg.isPending}
          >
            Create organization
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
            Dashboard
          </h1>
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            Overview of your declared catalog and data sources.
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

      {primaryOrg && (
        <div className="flex items-center justify-between border border-zinc-200/80 dark:border-zinc-700/40 rounded-lg px-4 py-3">
          <div className="flex items-center gap-3">
            <Building2 className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
            <div>
              <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
                {primaryOrg.name}
              </div>
              <div className="text-[11px] text-zinc-400 dark:text-zinc-500">
                {teamCount} teams · {serviceCount} services · {sourceCount} sources
              </div>
            </div>
          </div>
          <Link to="/orgs/$orgId" params={{ orgId: primaryOrg.id }}>
            <Button variant="secondary" size="sm" icon={<ChevronRight className="w-3.5 h-3.5" />}>
              Manage
            </Button>
          </Link>
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
        <Link to="/sources/new">
          <Button variant="secondary" size="sm" icon={<Plug className="w-3.5 h-3.5" />}>
            Add source
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
              <Link
                key={team.team_id ?? team.team}
                to={team.team_id ? "/teams/$teamId" : "/"}
                params={team.team_id ? { teamId: team.team_id } : undefined}
                className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Users className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
                  <div>
                    <span className="text-[13px] font-medium text-zinc-700 dark:text-zinc-300 group-hover:text-[var(--color-accent)] dark:group-hover:text-[var(--color-accent-dark)] transition-colors">
                      {team.team}
                    </span>
                    {team.services && team.services.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {team.services.slice(0, 6).map((svc) => (
                          <Badge key={svc} variant="neutral" size="sm">
                            {svc}
                          </Badge>
                        ))}
                        {team.services.length > 6 && (
                          <span className="text-[10px] text-zinc-400 dark:text-zinc-500 pl-1">
                            +{team.services.length - 6}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
                <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                  {team.services?.length ?? 0} services
                </span>
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/30 pt-6">
          <EmptyState
            icon={<Users className="w-10 h-10" />}
            title="No teams declared yet"
            description="Teams are the pivot for scoped retrieval. Add one to start attaching services and sources."
            action={
              primaryOrg ? (
                <Link to="/orgs/$orgId" params={{ orgId: primaryOrg.id }}>
                  <Button size="sm">Add a team</Button>
                </Link>
              ) : null
            }
          />
        </div>
      )}

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
    </div>
  );
}
