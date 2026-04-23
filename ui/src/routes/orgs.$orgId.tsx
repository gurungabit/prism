import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { Plus, Users, Plug, ArrowLeft, Trash2 } from "lucide-react";

import { Button } from "../components/shared/Button";
import { Input, Textarea } from "../components/shared/Input";
import { Badge } from "../components/shared/Badge";
import { Skeleton } from "../components/shared/Skeleton";
import { EmptyState } from "../components/shared/EmptyState";
import { useConfirm } from "../components/shared/ConfirmDialog";
import { DeclaredSourceRow } from "../components/sources/DeclaredSourceRow";
import {
  useCreateTeam,
  useDeclaredSources,
  useDeleteTeam,
  useOrg,
  useTeamsForOrg,
} from "../hooks/useCatalog";

export function OrgDetailPage() {
  const { orgId } = useParams({ strict: false }) as { orgId: string };
  const org = useOrg(orgId);
  const teams = useTeamsForOrg(orgId);
  const orgSources = useDeclaredSources({ orgId });
  const createTeam = useCreateTeam();
  const deleteTeam = useDeleteTeam();
  const confirm = useConfirm();

  const [showTeamForm, setShowTeamForm] = useState(false);
  const [teamName, setTeamName] = useState("");
  const [teamDescription, setTeamDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const teamList = teams.data?.teams ?? [];
  const orgSourceList = orgSources.data?.sources ?? [];

  if (org.isLoading) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8 space-y-6">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!org.data) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8">
        <EmptyState
          title="Organization not found"
          description="It may have been deleted."
          action={
            <Link to="/">
              <Button>Back to dashboard</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Dashboard
          </Link>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100 mt-1">
            {org.data.name}
          </h1>
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            Organization · {teamList.length} teams · {orgSourceList.length} org-level
            sources
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/sources/new" search={{ scope: "org", scopeId: orgId }}>
            <Button variant="secondary" size="sm" icon={<Plug className="w-3.5 h-3.5" />}>
              Add org-level source
            </Button>
          </Link>
        </div>
      </div>

      {/* Teams */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Teams
          </h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => setShowTeamForm((v) => !v)}
          >
            {showTeamForm ? "Cancel" : "Add team"}
          </Button>
        </div>

        {showTeamForm && (
          <form
            className="space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4"
            onSubmit={async (event) => {
              event.preventDefault();
              setFormError(null);
              if (!teamName.trim()) {
                setFormError("Team name is required");
                return;
              }
              try {
                await createTeam.mutateAsync({
                  orgId,
                  body: { name: teamName.trim(), description: teamDescription.trim() },
                });
                setTeamName("");
                setTeamDescription("");
                setShowTeamForm(false);
              } catch (err) {
                setFormError(err instanceof Error ? err.message : "Failed to create team");
              }
            }}
          >
            <Input
              label="Team name"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              error={formError ?? undefined}
              autoFocus
            />
            <Textarea
              label="Description"
              value={teamDescription}
              onChange={(e) => setTeamDescription(e.target.value)}
              rows={2}
            />
            <Button type="submit" size="sm" loading={createTeam.isPending}>
              Create
            </Button>
          </form>
        )}

        {teams.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : teamList.length > 0 ? (
          <div className="space-y-0">
            {teamList.map((team) => (
              <div
                key={team.id}
                className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group"
              >
                <Link
                  to="/teams/$teamId"
                  params={{ teamId: team.id }}
                  className="flex-1 min-w-0 flex items-center gap-2"
                >
                  <Users className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
                  <div>
                    <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
                      {team.name}
                    </span>
                    {team.description && (
                      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">
                        {team.description}
                      </p>
                    )}
                  </div>
                </Link>
                <button
                  onClick={async () => {
                    const ok = await confirm({
                      title: `Delete team '${team.name}'?`,
                      message: "This cannot be undone. Services, sources, and docs under this team will be removed.",
                      confirmLabel: "Delete team",
                      variant: "danger",
                    });
                    if (!ok) return;
                    await deleteTeam.mutateAsync(team.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-rose-500 transition-opacity p-1"
                  aria-label="Delete team"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            No teams yet. Add your first team above.
          </p>
        )}
      </section>

      {/* Org-level sources */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Org-level sources
          </h2>
          <Badge variant="info" size="sm">
            visible to every team
          </Badge>
        </div>
        {orgSources.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : orgSourceList.length > 0 ? (
          <div>
            {orgSourceList.map((src) => (
              <DeclaredSourceRow key={src.id} source={src} />
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            None attached. Docs here are visible to every team in the org —
            good for things like a global engineering handbook.
          </p>
        )}
      </section>
    </div>
  );
}
