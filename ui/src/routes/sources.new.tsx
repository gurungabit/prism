import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  CircleAlert,
  Users,
  Boxes,
  Plug,
} from "lucide-react";

import { Button } from "../components/shared/Button";
import { Input } from "../components/shared/Input";
import { Badge } from "../components/shared/Badge";
import { EmptyState } from "../components/shared/EmptyState";
import { Skeleton } from "../components/shared/Skeleton";
import { GitlabProjectSelect } from "../components/sources/GitlabProjectSelect";
import {
  useCreateSource,
  useOrgs,
  useServicesForTeam,
  useTeamsForOrg,
  useTriggerIngest,
  useValidateSource,
} from "../hooks/useCatalog";
import type { SourceKind, SourceScope } from "../lib/api";

type Step = 1 | 2 | 3 | 4;

/**
 * 4-step wizard:
 *
 *   1. Pick scope (org/team/service) and which one.
 *   2. Pick connector kind (only gitlab is live in Phase 1).
 *   3. Fill in kind-specific config (PAT, group/project path).
 *   4. Test connection, save, and trigger ingestion.
 *
 * If the caller lands here with ?scope=team&scopeId=<uuid> in the URL (e.g.
 * from a team detail page's "Add team-level source" button) we skip step 1.
 */
export function NewSourcePage() {
  const prefill = useSearch({ strict: false }) as {
    scope?: SourceScope;
    scopeId?: string;
  };
  const navigate = useNavigate();

  const orgs = useOrgs();

  const [step, setStep] = useState<Step>(prefill.scope && prefill.scopeId ? 2 : 1);
  const [scope, setScope] = useState<SourceScope>(prefill.scope ?? "service");
  const [scopeId, setScopeId] = useState<string>(prefill.scopeId ?? "");

  const [kind, setKind] = useState<SourceKind>("gitlab");
  const [sourceName, setSourceName] = useState("");
  const [token, setToken] = useState("");

  // GitLab config
  const [gitlabMode, setGitlabMode] = useState<"project" | "group">("project");
  const [projectPath, setProjectPath] = useState("");
  const [groupPath, setGroupPath] = useState("");
  const [gitRef, setGitRef] = useState("");
  const [includeSubgroups, setIncludeSubgroups] = useState(true);
  const [baseUrl, setBaseUrl] = useState("");

  // Path-based connectors (stubs in Phase 1)
  const [localPath, setLocalPath] = useState("");

  const [globalError, setGlobalError] = useState<string | null>(null);

  const validate = useValidateSource();
  const create = useCreateSource();
  const triggerIngest = useTriggerIngest();

  const firstOrg = orgs.data?.orgs[0];
  const teamsQuery = useTeamsForOrg(firstOrg?.id);

  // Lookup for services: we need them per-team, but users pick across all
  // teams in the scope-picker, so flatten once teams load.
  const teamList = teamsQuery.data?.teams ?? [];
  // Fetch services for every team in parallel. Because the number of teams is
  // usually small, this is fine in Phase 1; a dedicated /org/{id}/services
  // endpoint would be cleaner later.
  // We do this inline with the map below.

  const orgOptions = orgs.data?.orgs ?? [];

  const builtConfig = useMemo(() => {
    if (kind === "gitlab") {
      const base: Record<string, unknown> = {};
      if (baseUrl.trim()) base.base_url = baseUrl.trim();
      if (gitlabMode === "project") {
        base.project_path = projectPath.trim();
        if (gitRef.trim()) base.ref = gitRef.trim();
      } else {
        base.group_path = groupPath.trim();
        base.include_subgroups = includeSubgroups;
      }
      return base;
    }
    return { path: localPath.trim() };
  }, [kind, baseUrl, gitlabMode, projectPath, groupPath, gitRef, includeSubgroups, localPath]);

  // Derive a sensible default name once the user has config + scope.
  useEffect(() => {
    if (sourceName) return;
    if (kind === "gitlab") {
      const path = gitlabMode === "project" ? projectPath : groupPath;
      if (path) setSourceName(`GitLab: ${path}`);
    }
  }, [kind, gitlabMode, projectPath, groupPath, sourceName]);

  const canAdvanceStep1 = Boolean(scope && scopeId);
  const canAdvanceStep2 = Boolean(kind);
  const canAdvanceStep3 =
    kind === "gitlab"
      ? (gitlabMode === "project" ? projectPath.trim() : groupPath.trim()).length > 0
      : localPath.trim().length > 0;

  async function runValidate() {
    setGlobalError(null);
    try {
      const result = await validate.mutateAsync({
        kind,
        config: builtConfig,
        token: token.trim() || undefined,
      });
      return result;
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Validation failed");
      throw err;
    }
  }

  async function saveAndIngest() {
    setGlobalError(null);
    if (!sourceName.trim()) {
      setGlobalError("Source name is required");
      return;
    }
    try {
      const created = await create.mutateAsync({
        scope,
        scope_id: scopeId,
        kind,
        name: sourceName.trim(),
        config: builtConfig,
        token: token.trim() || undefined,
      });
      await triggerIngest.mutateAsync({ sourceId: created.id });
      navigate({ to: "/sources/$sourceId", params: { sourceId: created.id } });
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Failed to create source");
    }
  }

  if (orgs.isLoading) {
    return (
      <div className="max-w-[640px] mx-auto px-6 py-10 space-y-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!firstOrg) {
    return (
      <div className="max-w-[640px] mx-auto px-6 py-10">
        <EmptyState
          icon={<Plug className="w-10 h-10" />}
          title="Set up your organization first"
          description="A source has to hang off of an org, a team, or a service. Declare at least one before attaching a source."
          action={
            <Link to="/">
              <Button>Create your org</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="max-w-[720px] mx-auto px-6 py-10 space-y-8">
      <div>
        <Link
          to="/sources"
          className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300"
        >
          <ArrowLeft className="w-3 h-3" /> All sources
        </Link>
        <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100 mt-1">
          Add a data source
        </h1>
        <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
          Step {step} of 4 — ingested documents inherit the scope you choose.
        </p>
      </div>

      {/* Step 1: scope */}
      {step === 1 && (
        <div className="space-y-4">
          <p className="text-[13px] text-zinc-700 dark:text-zinc-300">Where should this source attach?</p>

          <div className="space-y-2">
            {orgOptions.map((org) => (
              <button
                key={org.id}
                type="button"
                onClick={() => {
                  setScope("org");
                  setScopeId(org.id);
                }}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-left transition-colors ${
                  scope === "org" && scopeId === org.id
                    ? "border-[var(--color-accent)] bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
                    : "border-zinc-200 dark:border-zinc-700/40 hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
                }`}
              >
                <Building2 className="w-4 h-4 text-zinc-400" />
                <div className="flex-1">
                  <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">{org.name}</div>
                  <div className="text-[11px] text-zinc-400 dark:text-zinc-500">
                    Org — docs visible to every team
                  </div>
                </div>
                {scope === "org" && scopeId === org.id && (
                  <CheckCircle2 className="w-4 h-4 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
                )}
              </button>
            ))}
          </div>

          <div className="space-y-1">
            <p className="text-[11px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mt-4">
              Teams
            </p>
            {teamsQuery.isLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : teamList.length === 0 ? (
              <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
                No teams yet.{" "}
                <Link
                  to="/orgs/$orgId"
                  params={{ orgId: firstOrg.id }}
                  className="text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline"
                >
                  Create one
                </Link>
              </p>
            ) : (
              teamList.map((team) => (
                <ScopeTeamRow
                  key={team.id}
                  teamId={team.id}
                  teamName={team.name}
                  selectedScope={scope}
                  selectedScopeId={scopeId}
                  onSelectTeam={() => {
                    setScope("team");
                    setScopeId(team.id);
                  }}
                  onSelectService={(serviceId) => {
                    setScope("service");
                    setScopeId(serviceId);
                  }}
                />
              ))
            )}
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-zinc-200/60 dark:border-zinc-700/30">
            <Button
              icon={<ArrowRight className="w-3.5 h-3.5" />}
              disabled={!canAdvanceStep1}
              onClick={() => setStep(2)}
            >
              Next: connector
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: kind */}
      {step === 2 && (
        <div className="space-y-4">
          <p className="text-[13px] text-zinc-700 dark:text-zinc-300">Pick a connector.</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <KindCard
              active={kind === "gitlab"}
              title="GitLab"
              description="Live API. Ingest READMEs, runbooks, docs/ from a group or single project."
              onSelect={() => setKind("gitlab")}
              badge="Live"
              badgeVariant="success"
            />
            <KindCard
              active={kind === "sharepoint"}
              title="SharePoint"
              description="Phase 1 stub — reads from a local export path. Full Graph integration in Phase 2."
              onSelect={() => setKind("sharepoint")}
              badge="Local only"
              badgeVariant="warning"
            />
            <KindCard
              active={kind === "excel"}
              title="Excel"
              description="Local xlsx/csv files. Good for service catalogs and team rosters."
              onSelect={() => setKind("excel")}
              badge="Local only"
              badgeVariant="warning"
            />
            <KindCard
              active={kind === "onenote"}
              title="OneNote"
              description="Local OneNote HTML export. Full connector in Phase 2."
              onSelect={() => setKind("onenote")}
              badge="Local only"
              badgeVariant="warning"
            />
          </div>

          <div className="flex justify-between gap-2 pt-4 border-t border-zinc-200/60 dark:border-zinc-700/30">
            <Button variant="ghost" size="sm" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button
              icon={<ArrowRight className="w-3.5 h-3.5" />}
              disabled={!canAdvanceStep2}
              onClick={() => setStep(3)}
            >
              Next: config
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: config */}
      {step === 3 && (
        <div className="space-y-4">
          {kind === "gitlab" ? (
            <>
              <Input
                label="Source name"
                placeholder="How this appears in the sources list"
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
              />
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1.5 text-[12px] text-zinc-600 dark:text-zinc-400">
                  <input
                    type="radio"
                    name="gitlab-mode"
                    checked={gitlabMode === "project"}
                    onChange={() => setGitlabMode("project")}
                  />
                  Single project
                </label>
                <label className="flex items-center gap-1.5 text-[12px] text-zinc-600 dark:text-zinc-400">
                  <input
                    type="radio"
                    name="gitlab-mode"
                    checked={gitlabMode === "group"}
                    onChange={() => setGitlabMode("group")}
                  />
                  Whole group
                </label>
              </div>
              <Input
                label="Personal access token"
                type="password"
                placeholder="glpat-… (read_api + read_repository scopes)"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />

              <Input
                label="Base URL (optional)"
                placeholder="https://gitlab.com/api/v4 — change for self-hosted"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />

              {gitlabMode === "project" ? (
                <>
                  <GitlabProjectSelect
                    value={projectPath}
                    onChange={setProjectPath}
                    token={token}
                    baseUrl={baseUrl}
                  />
                  <Input
                    label="Ref (optional)"
                    placeholder="main — defaults to project's default branch"
                    value={gitRef}
                    onChange={(e) => setGitRef(e.target.value)}
                  />
                </>
              ) : (
                <>
                  <Input
                    label="Group path"
                    placeholder="platform-team"
                    value={groupPath}
                    onChange={(e) => setGroupPath(e.target.value)}
                  />
                  <label className="flex items-center gap-2 text-[12px] text-zinc-600 dark:text-zinc-400">
                    <input
                      type="checkbox"
                      checked={includeSubgroups}
                      onChange={(e) => setIncludeSubgroups(e.target.checked)}
                    />
                    Include subgroups
                  </label>
                </>
              )}
            </>
          ) : (
            <>
              <Input
                label="Source name"
                placeholder="How this appears in the sources list"
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
              />
              <Input
                label="Local path"
                placeholder="/path/to/documents"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
              />
            </>
          )}

          {globalError && (
            <div className="flex items-start gap-2 text-[12px] text-rose-600 dark:text-rose-400 bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200/60 dark:border-rose-700/40 rounded-md p-3">
              <CircleAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{globalError}</span>
            </div>
          )}

          <div className="flex justify-between gap-2 pt-4 border-t border-zinc-200/60 dark:border-zinc-700/30">
            <Button variant="ghost" size="sm" onClick={() => setStep(2)}>
              Back
            </Button>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                loading={validate.isPending}
                disabled={!canAdvanceStep3}
                onClick={async () => {
                  try {
                    await runValidate();
                    setStep(4);
                  } catch {
                    // error already surfaced
                  }
                }}
              >
                Test connection
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: confirm + save */}
      {step === 4 && (
        <div className="space-y-4">
          <div className="rounded-lg border border-emerald-200 dark:border-emerald-700/40 bg-emerald-50/60 dark:bg-emerald-950/30 p-4 flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mt-0.5" />
            <div className="space-y-1">
              <p className="text-[13px] font-medium text-emerald-700 dark:text-emerald-300">
                Connection OK
              </p>
              {validate.data?.projects && validate.data.projects.length > 0 && (
                <p className="text-[11px] text-emerald-700/80 dark:text-emerald-300/80">
                  Found {validate.data.total_projects ?? validate.data.projects.length} project(s).
                </p>
              )}
            </div>
          </div>

          <dl className="space-y-2 text-[12px] text-zinc-600 dark:text-zinc-400">
            <ConfigRow label="Scope">
              {scope} · {scopeId}
            </ConfigRow>
            <ConfigRow label="Kind">{kind}</ConfigRow>
            <ConfigRow label="Name">{sourceName || "(unset)"}</ConfigRow>
            <ConfigRow label="Config">
              <pre className="font-mono text-[11px] bg-zinc-50 dark:bg-zinc-800/60 rounded px-2 py-1 overflow-x-auto">
                {JSON.stringify(builtConfig, null, 2)}
              </pre>
            </ConfigRow>
          </dl>

          {globalError && (
            <div className="flex items-start gap-2 text-[12px] text-rose-600 dark:text-rose-400 bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200/60 dark:border-rose-700/40 rounded-md p-3">
              <CircleAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{globalError}</span>
            </div>
          )}

          <div className="flex justify-between gap-2 pt-4 border-t border-zinc-200/60 dark:border-zinc-700/30">
            <Button variant="ghost" size="sm" onClick={() => setStep(3)}>
              Back
            </Button>
            <Button
              icon={<Plug className="w-3.5 h-3.5" />}
              loading={create.isPending || triggerIngest.isPending}
              onClick={saveAndIngest}
            >
              Save & ingest now
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function ConfigRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <dt className="w-24 text-[11px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 pt-0.5">
        {label}
      </dt>
      <dd className="flex-1 text-[12px] text-zinc-700 dark:text-zinc-300">{children}</dd>
    </div>
  );
}

function KindCard({
  active,
  title,
  description,
  onSelect,
  badge,
  badgeVariant,
}: {
  active: boolean;
  title: string;
  description: string;
  onSelect: () => void;
  badge: string;
  badgeVariant: "success" | "warning";
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`text-left rounded-lg border px-4 py-3 transition-colors ${
        active
          ? "border-[var(--color-accent)] bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
          : "border-zinc-200 dark:border-zinc-700/40 hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">{title}</div>
        <Badge variant={badgeVariant} size="sm">
          {badge}
        </Badge>
      </div>
      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-1 leading-relaxed">
        {description}
      </p>
    </button>
  );
}

function ScopeTeamRow({
  teamId,
  teamName,
  selectedScope,
  selectedScopeId,
  onSelectTeam,
  onSelectService,
}: {
  teamId: string;
  teamName: string;
  selectedScope: SourceScope;
  selectedScopeId: string;
  onSelectTeam: () => void;
  onSelectService: (serviceId: string) => void;
}) {
  const services = useServicesForTeam(teamId);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-zinc-200/80 dark:border-zinc-700/40 rounded-lg">
      <div className="flex items-center">
        <button
          type="button"
          onClick={onSelectTeam}
          className={`flex-1 flex items-center gap-3 px-4 py-2 text-left transition-colors ${
            selectedScope === "team" && selectedScopeId === teamId
              ? "bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)] rounded-l-lg"
              : "hover:bg-zinc-50 dark:hover:bg-zinc-800/30 rounded-l-lg"
          }`}
        >
          <Users className="w-3.5 h-3.5 text-zinc-400" />
          <div>
            <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
              {teamName}
            </div>
            <div className="text-[11px] text-zinc-400 dark:text-zinc-500">Team scope</div>
          </div>
          {selectedScope === "team" && selectedScopeId === teamId && (
            <CheckCircle2 className="w-3.5 h-3.5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] ml-auto" />
          )}
        </button>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="px-3 py-2 text-[11px] text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 border-l border-zinc-200 dark:border-zinc-700/40"
        >
          {expanded ? "Hide services" : "Pick service…"}
        </button>
      </div>
      {expanded && (
        <div className="border-t border-zinc-200/60 dark:border-zinc-700/30 px-4 py-2">
          {services.isLoading ? (
            <Skeleton className="h-8 w-full" />
          ) : (services.data?.services ?? []).length === 0 ? (
            <p className="text-[11px] text-zinc-400 dark:text-zinc-500 py-1">
              No services declared for this team yet.
            </p>
          ) : (
            <div className="space-y-1">
              {services.data!.services.map((svc) => (
                <button
                  key={svc.id}
                  type="button"
                  onClick={() => onSelectService(svc.id)}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 text-left rounded-md transition-colors ${
                    selectedScope === "service" && selectedScopeId === svc.id
                      ? "bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
                      : "hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
                  }`}
                >
                  <Boxes className="w-3 h-3 text-zinc-400" />
                  <span className="text-[12px] text-zinc-800 dark:text-zinc-200">{svc.name}</span>
                  {selectedScope === "service" && selectedScopeId === svc.id && (
                    <CheckCircle2 className="w-3 h-3 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] ml-auto" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
