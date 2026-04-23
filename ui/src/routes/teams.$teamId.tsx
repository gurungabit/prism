import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, Boxes, Plug, Plus, Trash2 } from "lucide-react";

import { Button } from "../components/shared/Button";
import { Input, Textarea } from "../components/shared/Input";
import { Badge } from "../components/shared/Badge";
import { Skeleton } from "../components/shared/Skeleton";
import { EmptyState } from "../components/shared/EmptyState";
import { useConfirm } from "../components/shared/ConfirmDialog";
import { DeclaredSourceRow } from "../components/sources/DeclaredSourceRow";
import {
  useCreateService,
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
  const createService = useCreateService();
  const deleteService = useDeleteService();
  const confirm = useConfirm();

  const [showForm, setShowForm] = useState(false);
  const [serviceName, setServiceName] = useState("");
  const [serviceRepo, setServiceRepo] = useState("");
  const [serviceDescription, setServiceDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

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
          <Link
            to="/orgs/$orgId"
            params={{ orgId: team.data.org_id }}
            className="inline-flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Org
          </Link>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100 mt-1">
            {team.data.name}
          </h1>
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
          <form
            className="space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4"
            onSubmit={async (event) => {
              event.preventDefault();
              setFormError(null);
              if (!serviceName.trim()) {
                setFormError("Service name is required");
                return;
              }
              try {
                await createService.mutateAsync({
                  teamId,
                  body: {
                    name: serviceName.trim(),
                    repo_url: serviceRepo.trim(),
                    description: serviceDescription.trim(),
                  },
                });
                setServiceName("");
                setServiceRepo("");
                setServiceDescription("");
                setShowForm(false);
              } catch (err) {
                setFormError(err instanceof Error ? err.message : "Failed to create service");
              }
            }}
          >
            <Input
              label="Service name"
              value={serviceName}
              onChange={(e) => setServiceName(e.target.value)}
              error={formError ?? undefined}
              autoFocus
            />
            <Input
              label="Repository URL"
              placeholder="https://gitlab.com/..."
              value={serviceRepo}
              onChange={(e) => setServiceRepo(e.target.value)}
            />
            <Textarea
              label="Description"
              value={serviceDescription}
              onChange={(e) => setServiceDescription(e.target.value)}
              rows={2}
            />
            <Button type="submit" size="sm" loading={createService.isPending}>
              Create
            </Button>
          </form>
        )}

        {services.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : serviceList.length > 0 ? (
          <div className="space-y-0">
            {serviceList.map((service) => (
              <div
                key={service.id}
                className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group"
              >
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
