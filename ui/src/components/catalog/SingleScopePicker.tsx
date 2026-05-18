import { useEffect, useState } from "react";
import { Boxes, Building2, CheckCircle2, Users } from "lucide-react";

import { useOrgs, useServicesForTeam, useTeamsForOrg } from "../../hooks/useCatalog";
import type { SourceScope } from "../../lib/api";
import { Skeleton } from "../shared/Skeleton";

export interface SingleScopeValue {
  scope: SourceScope;
  scopeId: string;
}

interface Props {
  value: SingleScopeValue;
  onChange: (value: SingleScopeValue) => void;
}

export function SingleScopePicker({ value, onChange }: Props) {
  const orgs = useOrgs();
  const orgList = orgs.data?.orgs ?? [];
  const [selectedOrgId, setSelectedOrgId] = useState("");

  useEffect(() => {
    if (!selectedOrgId && orgList[0]) {
      setSelectedOrgId(value.scope === "org" && value.scopeId ? value.scopeId : orgList[0].id);
    }
  }, [orgList, selectedOrgId, value.scope, value.scopeId]);

  const teams = useTeamsForOrg(selectedOrgId || undefined);
  const teamList = teams.data?.teams ?? [];

  if (orgs.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {orgList.map((org) => (
          <button
            key={org.id}
            type="button"
            onClick={() => {
              setSelectedOrgId(org.id);
              onChange({ scope: "org", scopeId: org.id });
            }}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-md border text-left transition-colors ${
              value.scope === "org" && value.scopeId === org.id
                ? "border-[var(--color-accent)] bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
                : "border-zinc-200 dark:border-zinc-700/40 hover:bg-zinc-100 dark:hover:bg-zinc-800/30"
            }`}
          >
            <Building2 className="w-3.5 h-3.5 text-zinc-400" />
            <span className="flex-1 text-[13px] text-zinc-800 dark:text-zinc-200">
              {org.name}
            </span>
            {value.scope === "org" && value.scopeId === org.id && (
              <CheckCircle2 className="w-3.5 h-3.5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
            )}
          </button>
        ))}
      </div>

      {selectedOrgId && (
        <div className="space-y-2">
          {teams.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            teamList.map((team) => (
              <ScopeTeamOption
                key={team.id}
                teamId={team.id}
                teamName={team.name}
                value={value}
                onChange={onChange}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ScopeTeamOption({
  teamId,
  teamName,
  value,
  onChange,
}: {
  teamId: string;
  teamName: string;
  value: SingleScopeValue;
  onChange: (value: SingleScopeValue) => void;
}) {
  const [open, setOpen] = useState(false);
  const services = useServicesForTeam(teamId);
  const serviceList = services.data?.services ?? [];

  return (
    <div className="rounded-md border border-zinc-200/80 dark:border-zinc-700/40 overflow-hidden">
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => onChange({ scope: "team", scopeId: teamId })}
          className={`flex-1 flex items-center gap-2 px-3 py-2 text-left transition-colors ${
            value.scope === "team" && value.scopeId === teamId
              ? "bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
              : "hover:bg-zinc-100 dark:hover:bg-zinc-800/30"
          }`}
        >
          <Users className="w-3.5 h-3.5 text-zinc-400" />
          <span className="flex-1 text-[13px] text-zinc-800 dark:text-zinc-200">
            {teamName}
          </span>
          {value.scope === "team" && value.scopeId === teamId && (
            <CheckCircle2 className="w-3.5 h-3.5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
          )}
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="px-3 py-2 text-[11px] text-zinc-500 dark:text-zinc-400 border-l border-zinc-200 dark:border-zinc-700/40 hover:bg-zinc-100 dark:hover:bg-zinc-800/30"
        >
          {open ? "Hide" : "Services"}
        </button>
      </div>

      {open && (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/30 p-2 space-y-1">
          {services.isLoading ? (
            <Skeleton className="h-8 w-full" />
          ) : serviceList.length === 0 ? (
            <p className="text-[11px] text-zinc-400 dark:text-zinc-500 px-1 py-1">
              No services declared for this team.
            </p>
          ) : (
            serviceList.map((service) => (
              <button
                key={service.id}
                type="button"
                onClick={() => onChange({ scope: "service", scopeId: service.id })}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition-colors ${
                  value.scope === "service" && value.scopeId === service.id
                    ? "bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
                    : "hover:bg-zinc-100 dark:hover:bg-zinc-800/30"
                }`}
              >
                <Boxes className="w-3 h-3 text-zinc-400" />
                <span className="flex-1 text-[12px] text-zinc-700 dark:text-zinc-300">
                  {service.name}
                </span>
                {value.scope === "service" && value.scopeId === service.id && (
                  <CheckCircle2 className="w-3 h-3 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
