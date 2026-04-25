import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { Combobox } from "../shared/Combobox";
import { Skeleton } from "../shared/Skeleton";
import { useOrgs, useTeamsForOrg } from "../../hooks/useCatalog";
import { listServicesForTeam } from "../../lib/api";

export interface ScopeValue {
  org_id?: string;
  team_ids: string[];
  service_ids: string[];
}

interface Props {
  value: ScopeValue;
  onChange: (value: ScopeValue) => void;
  // Compact = single-line ish; Full = stacked card layout.
  compact?: boolean;
}

// Catalog-backed scope picker shared between Analyze, Search, and Chat.
//
// Behavior:
// - Auto-pins to the only org when one exists; renders a dropdown if there
//   are multiple. ``org_id`` is the gate -- without it the backend ignores
//   the scope entirely.
// - ``team_ids`` is a multi-select of the chosen org's teams. Empty means
//   "all teams" within the org.
// - ``service_ids`` is a multi-select across the *selected* teams' services
//   (or all teams if none selected). Empty means "all services".
//
// The shape we emit matches the API's ``scope`` field on Search/Chat and the
// top-level ``org_id`` / ``team_ids`` / ``service_ids`` on Analyze.
export function ScopeSelector({ value, onChange, compact = false }: Props) {
  const orgs = useOrgs();
  const orgList = orgs.data?.orgs ?? [];

  // Auto-pin org_id when there's exactly one org and the user hasn't picked.
  useEffect(() => {
    const only = orgList.length === 1 ? orgList[0] : undefined;
    if (!value.org_id && only) {
      onChange({ ...value, org_id: only.id });
    }
  }, [orgList, value, onChange]);

  const teams = useTeamsForOrg(value.org_id);
  const teamList = teams.data?.teams ?? [];

  // Fetch services for every team in the selected org so the service picker
  // is one cached query rather than N. ``enabled`` keeps it idle until
  // an org is set, matching the rest of the form's gating.
  const services = useQuery({
    queryKey: ["services-for-org", value.org_id],
    enabled: !!value.org_id && teamList.length > 0,
    staleTime: 30_000,
    queryFn: async () => {
      const responses = await Promise.all(
        teamList.map((t) => listServicesForTeam(t.id)),
      );
      return responses.flatMap((r) => r.services);
    },
  });
  const serviceList = services.data ?? [];

  // The service multi-select is filtered to teams that are either in the
  // selected ``team_ids`` set or all teams when no team filter is on.
  const visibleServices = useMemo(() => {
    if (value.team_ids.length === 0) return serviceList;
    const allow = new Set(value.team_ids);
    return serviceList.filter((s) => allow.has(s.team_id));
  }, [serviceList, value.team_ids]);

  // Drop service selections that are no longer visible (e.g. user
  // deselected the parent team).
  useEffect(() => {
    if (value.service_ids.length === 0) return;
    const visibleIds = new Set(visibleServices.map((s) => s.id));
    const filtered = value.service_ids.filter((id) => visibleIds.has(id));
    if (filtered.length !== value.service_ids.length) {
      onChange({ ...value, service_ids: filtered });
    }
  }, [visibleServices, value, onChange]);

  if (orgs.isLoading) {
    return <Skeleton className="h-12 w-full" />;
  }

  if (orgList.length === 0) {
    return (
      <p className="text-[12px] text-zinc-500 dark:text-zinc-400">
        No organizations declared yet. Create one before scoping retrieval.
      </p>
    );
  }

  const labelClass =
    "block text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500";
  const wrapperClass = compact ? "space-y-2" : "space-y-3";

  return (
    <div className={wrapperClass}>
      {orgList.length > 1 && (
        <div className="space-y-1">
          <label className={labelClass}>Organization</label>
          <Combobox
            value={value.org_id ?? null}
            onChange={(orgId) =>
              onChange({
                org_id: orgId ?? undefined,
                // Reset team / service narrowing when the org changes since
                // those IDs are scoped to a specific org.
                team_ids: [],
                service_ids: [],
              })
            }
            options={orgList.map((o) => ({ id: o.id, label: o.name }))}
            placeholder="Search organizations…"
            emptyMessage="No organization matches that name."
          />
        </div>
      )}

      {value.org_id && (() => {
        const teamsLoading = teams.isLoading;
        const servicesLoading = services.isLoading;
        const noTeams = !teamsLoading && teamList.length === 0;
        const noServices = !servicesLoading && serviceList.length === 0;

        // When the pinned org has zero teams *and* zero services there
        // is nothing the user can narrow by. Showing the two
        // "leave blank for all" rows under that condition is
        // confusing -- they read as inert form fields with nothing to
        // pick. Replace them with a single empty-state hint that
        // points at the Organization page where the catalog gets
        // populated.
        if (noTeams && noServices) {
          return (
            <div className="rounded-md border border-dashed border-zinc-300/60 dark:border-zinc-700/40 px-3 py-2.5 text-[12px] text-zinc-500 dark:text-zinc-400">
              <p>
                This org has no teams or services declared yet, so the
                only available scope is the org itself.{" "}
                <Link
                  to="/organization"
                  className="text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline"
                >
                  Declare teams &amp; services
                </Link>{" "}
                to narrow retrieval further.
              </p>
            </div>
          );
        }

        return (
          <>
            <div className="space-y-1">
              <label className={labelClass}>
                Teams (optional, leave blank for all)
              </label>
              <MultiSelect
                options={teamList.map((t) => ({ id: t.id, label: t.name }))}
                selected={value.team_ids}
                onChange={(team_ids) =>
                  onChange({ ...value, team_ids, service_ids: [] })
                }
                loading={teamsLoading}
                placeholder={
                  noTeams
                    ? "No teams in this org yet"
                    : "Pick one or more teams…"
                }
              />
            </div>

            <div className="space-y-1">
              <label className={labelClass}>
                Services (optional, leave blank for all)
              </label>
              <MultiSelect
                options={visibleServices.map((s) => ({
                  id: s.id,
                  label: s.name,
                }))}
                selected={value.service_ids}
                onChange={(service_ids) =>
                  onChange({ ...value, service_ids })
                }
                loading={servicesLoading}
                placeholder={
                  visibleServices.length === 0
                    ? "No services in this scope"
                    : "Pick one or more services…"
                }
              />
            </div>
          </>
        );
      })()}
    </div>
  );
}

interface MultiSelectProps {
  options: { id: string; label: string }[];
  selected: string[];
  onChange: (ids: string[]) => void;
  loading?: boolean;
  placeholder?: string;
}

// Lightweight multi-select rendered as a wrapped row of toggle chips. Avoids
// pulling in a select-library dependency for what's a small list.
function MultiSelect({
  options,
  selected,
  onChange,
  loading,
  placeholder,
}: MultiSelectProps) {
  if (loading) {
    return <Skeleton className="h-8 w-full" />;
  }
  if (options.length === 0) {
    return (
      <p className="text-[11px] text-zinc-500 dark:text-zinc-400 py-1">
        {placeholder || "Nothing to pick from"}
      </p>
    );
  }
  const selectedSet = new Set(selected);
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => {
        const isOn = selectedSet.has(opt.id);
        return (
          <button
            type="button"
            key={opt.id}
            onClick={() => {
              if (isOn) {
                onChange(selected.filter((s) => s !== opt.id));
              } else {
                onChange([...selected, opt.id]);
              }
            }}
            className={`inline-flex items-center text-[12px] px-2.5 py-1 rounded-full border transition-colors duration-150 ${
              isOn
                ? "border-[var(--color-accent)] dark:border-[var(--color-accent-dark)] bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)] text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]"
                : "border-zinc-200 dark:border-zinc-700/50 text-zinc-600 dark:text-zinc-400 hover:border-zinc-300 dark:hover:border-zinc-600"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
