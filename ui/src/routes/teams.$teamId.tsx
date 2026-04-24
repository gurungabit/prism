import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, Boxes, Pencil, Plug, Plus, Trash2 } from "lucide-react";

import { Button } from "../components/shared/Button";
import { Badge } from "../components/shared/Badge";
import { Skeleton } from "../components/shared/Skeleton";
import { EmptyState } from "../components/shared/EmptyState";
import { useConfirm } from "../components/shared/ConfirmDialog";
import { DeclaredSourceRow } from "../components/sources/DeclaredSourceRow";
import { TeamForm } from "../components/catalog/TeamForm";
import { ServiceForm } from "../components/catalog/ServiceForm";
import {
  useDeclaredSources,
  useDeleteService,
  useServicesForTeam,
  useTeamById,
} from "../hooks/useCatalog";

export function TeamDetailPage() {
  const { teamId } = useParams({ strict: false }) as { teamId: string };
  const team = useTeamById(teamId);
  const services = useServicesForTeam(teamId);
  const teamSources = useDeclaredSources({ teamId });
  const deleteService = useDeleteService();
  const confirm = useConfirm();

  const [showForm, setShowForm] = useState(false);
  const [editingTeam, setEditingTeam] = useState(false);
  const [editingServiceId, setEditingServiceId] = useState<string | null>(null);

  const serviceList = services.data?.services ?? [];
  const teamSourceList = teamSources.data?.sources ?? [];

  if (team.isLoading) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8 space-y-6">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!team.data) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8">
        <EmptyState
          title="Team not found"
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
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </button>
          <div className="flex items-center gap-2 mt-1">
            <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
              {team.data.name}
            </h1>
            <button
              type="button"
              onClick={() => setEditingTeam((v) => !v)}
              className="p-1 rounded text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
              aria-label="Edit team"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          </div>
          {team.data.description && (
            <p className="text-[12px] text-zinc-500 dark:text-zinc-400 mt-1 max-w-xl">
              {team.data.description}
            </p>
          )}
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            {serviceList.length} services · {teamSourceList.length} team-level sources
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/sources/new" search={{ scope: "team", scopeId: teamId }}>
            <Button variant="secondary" size="sm" icon={<Plug className="w-3.5 h-3.5" />}>
              Add team-level source
            </Button>
          </Link>
        </div>
      </div>

      {editingTeam && (
        <TeamForm
          mode="edit"
          teamId={teamId}
          initialValues={{
            name: team.data.name,
            description: team.data.description ?? "",
          }}
          onSuccess={() => setEditingTeam(false)}
          onCancel={() => setEditingTeam(false)}
        />
      )}

      {/* Services */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Services
          </h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancel" : "Add service"}
          </Button>
        </div>

        {showForm && (
          <ServiceForm
            mode="create"
            teamId={teamId}
            onSuccess={() => setShowForm(false)}
            onCancel={() => setShowForm(false)}
          />
        )}

        {services.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : serviceList.length > 0 ? (
          <div className="space-y-0">
            {serviceList.map((service) => (
              <div key={service.id}>
                <div className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group">
                  <Link
                    to="/services/$serviceId"
                    params={{ serviceId: service.id }}
                    className="flex-1 min-w-0 flex items-center gap-2"
                  >
                    <Boxes className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
                          {service.name}
                        </span>
                        {service.repo_url && (
                          <Badge variant="neutral" size="sm">
                            repo
                          </Badge>
                        )}
                      </div>
                      {service.description && (
                        <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">
                          {service.description}
                        </p>
                      )}
                    </div>
                  </Link>
                  <button
                    onClick={() => setEditingServiceId(editingServiceId === service.id ? null : service.id)}
                    className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-opacity p-1"
                    aria-label="Edit service"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={async () => {
                      const ok = await confirm({
                        title: `Delete service '${service.name}'?`,
                        message: "Its sources, documents, and chunks will be cascaded.",
                        confirmLabel: "Delete service",
                        variant: "danger",
                      });
                      if (!ok) return;
                      await deleteService.mutateAsync(service.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-rose-500 transition-opacity p-1"
                    aria-label="Delete service"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                {editingServiceId === service.id && (
                  <div className="pb-3">
                    <ServiceForm
                      mode="edit"
                      serviceId={service.id}
                      initialValues={{
                        name: service.name,
                        repo_url: service.repo_url ?? "",
                        description: service.description ?? "",
                      }}
                      onSuccess={() => setEditingServiceId(null)}
                      onCancel={() => setEditingServiceId(null)}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            No services declared yet. Declare the services this team owns so
            documents can be scoped to them.
          </p>
        )}
      </section>

      {/* Team-level sources */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Team-level sources
          </h2>
          <Badge variant="info" size="sm">
            visible only to this team
          </Badge>
        </div>
        {teamSources.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : teamSourceList.length > 0 ? (
          <div>
            {teamSourceList.map((src) => (
              <DeclaredSourceRow key={src.id} source={src} />
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            None attached. Use team-level sources for team-wide docs that
            aren't tied to a specific service (onboarding, team-wide standards).
          </p>
        )}
      </section>
    </div>
  );
}
