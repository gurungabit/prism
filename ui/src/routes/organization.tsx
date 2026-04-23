import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronRight, Network } from "lucide-react";

import { Button } from "../components/shared/Button";
import { Skeleton } from "../components/shared/Skeleton";
import { EmptyState } from "../components/shared/EmptyState";
import { OrganizationGraph } from "../components/organization/OrganizationGraph";
import {
  NodeDetailPanel,
  type SelectedNode,
} from "../components/organization/NodeDetailPanel";
import { getOrganizationGraph, type OrganizationGraphResponse } from "../lib/api";

export function OrganizationPage() {
  const graph = useQuery({
    queryKey: ["organization-graph"],
    queryFn: getOrganizationGraph,
    staleTime: 30_000,
  });
  const [selected, setSelected] = useState<SelectedNode | null>(null);

  if (graph.isLoading) {
    return (
      <div className="max-w-[1400px] mx-auto px-6 py-8 space-y-6">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-[calc(100vh-200px)] w-full" />
      </div>
    );
  }

  if (graph.isError || !graph.data) {
    return (
      <div className="max-w-[720px] mx-auto px-6 py-16">
        <EmptyState
          icon={<Network className="w-10 h-10" />}
          title="Couldn't load the graph"
          description={graph.error instanceof Error ? graph.error.message : "Unknown error"}
        />
      </div>
    );
  }

  const hasNodes =
    graph.data.orgs.length > 0 || graph.data.teams.length > 0 || graph.data.services.length > 0;

  if (!hasNodes) {
    return (
      <div className="max-w-[720px] mx-auto px-6 py-16">
        <EmptyState
          icon={<Network className="w-10 h-10" />}
          title="Nothing to graph yet"
          description="Declare an organization, teams, and services to see them rendered here."
        />
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-4">
      <div>
        <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">Organization</h1>
        <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
          {graph.data.orgs.length} org · {graph.data.teams.length} teams ·{" "}
          {graph.data.services.length} services · {graph.data.dependencies.length} dependencies
        </p>
      </div>

      <OrgSummaryCards data={graph.data} />

      <OrganizationGraph data={graph.data} onSelect={setSelected} />

      <NodeDetailPanel
        selected={selected}
        data={graph.data}
        onClose={() => setSelected(null)}
      />

      <div className="flex items-center gap-6 text-[11px] text-zinc-500 dark:text-zinc-500">
        <span className="flex items-center gap-2">
          <span className="inline-block w-5 h-0.5 bg-zinc-500/50" />
          Hierarchy (owns)
        </span>
        <span className="flex items-center gap-2">
          <span
            className="inline-block w-5 h-0.5"
            style={{
              backgroundImage:
                "repeating-linear-gradient(90deg, var(--color-accent) 0 4px, transparent 4px 8px)",
            }}
          />
          Service dependency
        </span>
      </div>
    </div>
  );
}

// One row per org, showing team + service + source counts with a Manage
// button -- mirrors the same card that appears on the Dashboard. Useful
// shortcut on the Organization page so users don't have to interact with
// the graph just to open the catalog detail pages.
function OrgSummaryCards({ data }: { data: OrganizationGraphResponse }) {
  return (
    <div className="space-y-2">
      {data.orgs.map((org) => {
        const teamsForOrg = data.teams.filter((t) => t.org_id === org.id);
        const teamIds = new Set(teamsForOrg.map((t) => t.id));
        const servicesForOrg = data.services.filter((s) => teamIds.has(s.team_id));
        return (
          <div
            key={org.id}
            className="flex items-center justify-between border border-zinc-200/80 dark:border-zinc-700/40 rounded-lg px-4 py-3"
          >
            <div className="flex items-center gap-3">
              <Building2 className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
              <div>
                <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
                  {org.name}
                </div>
                <div className="text-[11px] text-zinc-400 dark:text-zinc-500">
                  {teamsForOrg.length} teams · {servicesForOrg.length} services
                </div>
              </div>
            </div>
            <Link to="/orgs/$orgId" params={{ orgId: org.id }}>
              <Button
                variant="secondary"
                size="sm"
                icon={<ChevronRight className="w-3.5 h-3.5" />}
              >
                Manage
              </Button>
            </Link>
          </div>
        );
      })}
    </div>
  );
}
