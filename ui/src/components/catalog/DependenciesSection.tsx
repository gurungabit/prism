import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Boxes, Plus, Trash2, Users } from "lucide-react";

import { Button } from "../shared/Button";
import { Skeleton } from "../shared/Skeleton";
import { useConfirm } from "../shared/ConfirmDialog";
import {
  useAddServiceDependency,
  useDeleteServiceDependency,
  useServiceDependencies,
} from "../../hooks/useCatalog";
import { getOrganizationGraph } from "../../lib/api";

interface Props {
  serviceId: string;
}

// "Dependencies" block rendered on the service detail page. Shows the
// service's outbound edges and lets the user add a new one by picking any
// other declared service (optionally scoped to a team via the group
// headers). Dependencies are user-managed now -- we no longer extract
// them from doc text.
export function DependenciesSection({ serviceId }: Props) {
  const deps = useServiceDependencies(serviceId);
  const addDep = useAddServiceDependency();
  const deleteDep = useDeleteServiceDependency();
  const confirm = useConfirm();

  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Fetching the org graph once gives us every service + team in one shot;
  // cheaper than chaining orgs -> teams -> services queries for a picker.
  const graph = useQuery({
    queryKey: ["organization-graph"],
    queryFn: getOrganizationGraph,
    enabled: showForm, // only fetch when the user opens the add form
    staleTime: 30_000,
  });

  const depList = deps.data?.dependencies ?? [];
  const existingTargetIds = useMemo(
    () => new Set(depList.map((d) => d.to_service_id)),
    [depList],
  );

  // Build the picker options: every service except this one and anything
  // already depended on, grouped by team for readability.
  const pickerOptions = useMemo(() => {
    if (!graph.data) return [] as { teamName: string; services: { id: string; name: string }[] }[];
    const byTeam = new Map<string, { teamName: string; services: { id: string; name: string }[] }>();
    const teamNameById = new Map(graph.data.teams.map((t) => [t.id, t.name]));
    for (const svc of graph.data.services) {
      if (svc.id === serviceId) continue;
      if (existingTargetIds.has(svc.id)) continue;
      const teamName = teamNameById.get(svc.team_id) ?? "Unknown team";
      let bucket = byTeam.get(svc.team_id);
      if (!bucket) {
        bucket = { teamName, services: [] };
        byTeam.set(svc.team_id, bucket);
      }
      bucket.services.push({ id: svc.id, name: svc.name });
    }
    return Array.from(byTeam.values())
      .map((b) => ({ teamName: b.teamName, services: b.services.sort((a, b) => a.name.localeCompare(b.name)) }))
      .sort((a, b) => a.teamName.localeCompare(b.teamName));
  }, [graph.data, serviceId, existingTargetIds]);

  async function submit() {
    setError(null);
    if (!selected) {
      setError("Pick a target service");
      return;
    }
    try {
      await addDep.mutateAsync({ serviceId, toServiceId: selected });
      setSelected("");
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add dependency");
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Dependencies
        </h2>
        <Button
          variant="ghost"
          size="sm"
          icon={<Plus className="w-3.5 h-3.5" />}
          onClick={() => {
            setShowForm((v) => !v);
            setError(null);
          }}
        >
          {showForm ? "Cancel" : "Add dependency"}
        </Button>
      </div>

      {showForm && (
        <div className="space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4">
          <div className="space-y-1.5">
            <label className="block text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              This service depends on
            </label>
            {graph.isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : pickerOptions.length === 0 ? (
              <p className="text-[12px] text-zinc-500 dark:text-zinc-400">
                No eligible services -- every other service is already a
                dependency (or none exist yet).
              </p>
            ) : (
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-600/50 bg-white dark:bg-[#1e1e20] text-zinc-900 dark:text-zinc-100 px-3 py-2 text-[13px] focus:outline-none focus:border-[var(--color-accent)] dark:focus:border-[var(--color-accent-dark)]"
              >
                <option value="">Select a service…</option>
                {pickerOptions.map((group) => (
                  <optgroup key={group.teamName} label={group.teamName}>
                    {group.services.map((svc) => (
                      <option key={svc.id} value={svc.id}>
                        {svc.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            )}
            {error && (
              <p className="text-[11px] text-rose-600 dark:text-rose-400">{error}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              loading={addDep.isPending}
              disabled={!selected || pickerOptions.length === 0}
              onClick={submit}
            >
              Add
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowForm(false);
                setSelected("");
                setError(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {deps.isLoading ? (
        <Skeleton className="h-12 w-full" />
      ) : depList.length === 0 ? (
        <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
          No dependencies declared yet. Click "Add dependency" to connect
          this service to another one.
        </p>
      ) : (
        <div className="space-y-0">
          {depList.map((dep) => (
            <div
              key={dep.to_service_id}
              className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Boxes className="w-4 h-4 text-zinc-400 dark:text-zinc-500 flex-shrink-0" />
                <div className="min-w-0">
                  <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
                    {dep.to_service_name}
                  </span>
                  {dep.team_name && (
                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500 ml-2 inline-flex items-center gap-1">
                      <Users className="w-3 h-3" /> {dep.team_name}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={async () => {
                  const ok = await confirm({
                    title: `Remove dependency on '${dep.to_service_name}'?`,
                    message: "The edge will be deleted; the services themselves stay intact.",
                    confirmLabel: "Remove",
                    variant: "danger",
                  });
                  if (!ok) return;
                  await deleteDep.mutateAsync({
                    serviceId,
                    toServiceId: dep.to_service_id,
                  });
                }}
                className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-rose-500 transition-opacity p-1"
                aria-label="Remove dependency"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
