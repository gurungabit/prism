import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Boxes, ExternalLink, Plus, Trash2, Users } from "lucide-react";

import { Button } from "../shared/Button";
import { Combobox, type ComboboxOption } from "../shared/Combobox";
import { Input, Textarea } from "../shared/Input";
import { Skeleton } from "../shared/Skeleton";
import { useConfirm } from "../shared/ConfirmDialog";
import {
  useAddExternalServiceDependency,
  useAddServiceDependency,
  useDeleteExternalServiceDependency,
  useDeleteServiceDependency,
  useServiceDependencies,
} from "../../hooks/useCatalog";
import { getOrganizationGraph, type ServiceDependency } from "../../lib/api";

interface Props {
  serviceId: string;
}

type FormKind = "service" | "external";

// "Dependencies" block on the service detail page. Two flavours:
//
//   - Catalog: pick a declared service from a searchable combobox grouped
//     by team. Edge wires to the target's UUID.
//   - External: free-text name + description for things outside the
//     declared catalog (Stripe, Auth0, an upstream team's API not yet
//     declared, etc.). No service_id; the row carries the description so
//     the team has somewhere to write a one-liner about why this dep
//     exists.
export function DependenciesSection({ serviceId }: Props) {
  const deps = useServiceDependencies(serviceId);
  const addCatalogDep = useAddServiceDependency();
  const addExternalDep = useAddExternalServiceDependency();
  const deleteCatalogDep = useDeleteServiceDependency();
  const deleteExternalDep = useDeleteExternalServiceDependency();
  const confirm = useConfirm();

  const [showForm, setShowForm] = useState(false);
  const [kind, setKind] = useState<FormKind>("service");
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [externalName, setExternalName] = useState("");
  const [externalDescription, setExternalDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const graph = useQuery({
    queryKey: ["organization-graph"],
    queryFn: getOrganizationGraph,
    enabled: showForm && kind === "service",
    staleTime: 30_000,
  });

  const depList = deps.data?.dependencies ?? [];
  const existingCatalogTargetIds = useMemo(
    () =>
      new Set(
        depList
          .filter((d) => d.kind === "service" && d.to_service_id)
          .map((d) => d.to_service_id as string),
      ),
    [depList],
  );
  const existingExternalNames = useMemo(
    () =>
      new Set(
        depList
          .filter((d) => d.kind === "external")
          .map((d) => d.to_service_name.toLowerCase()),
      ),
    [depList],
  );

  // Build Combobox options grouped by team. Disabled rows show selectable
  // services that are already linked so the user understands why they
  // can't pick them again instead of just having them disappear.
  const comboboxOptions = useMemo<ComboboxOption[]>(() => {
    if (!graph.data) return [];
    const teamNameById = new Map(graph.data.teams.map((t) => [t.id, t.name]));
    const opts: ComboboxOption[] = graph.data.services
      .filter((s) => s.id !== serviceId)
      .map((s) => ({
        id: s.id,
        label: s.name,
        hint: s.description || undefined,
        group: teamNameById.get(s.team_id) ?? "Unknown team",
        disabled: existingCatalogTargetIds.has(s.id),
      }));
    // Stable ordering so the visual list doesn't flicker between renders.
    opts.sort((a, b) => {
      const g = (a.group ?? "").localeCompare(b.group ?? "");
      if (g !== 0) return g;
      return a.label.localeCompare(b.label);
    });
    return opts;
  }, [graph.data, serviceId, existingCatalogTargetIds]);

  function resetForm() {
    setSelectedServiceId(null);
    setExternalName("");
    setExternalDescription("");
    setError(null);
    setKind("service");
  }

  async function submit() {
    setError(null);
    try {
      if (kind === "service") {
        if (!selectedServiceId) {
          setError("Pick a target service");
          return;
        }
        await addCatalogDep.mutateAsync({
          serviceId,
          toServiceId: selectedServiceId,
        });
      } else {
        const name = externalName.trim();
        if (!name) {
          setError("Name is required");
          return;
        }
        if (existingExternalNames.has(name.toLowerCase())) {
          setError("That external dependency is already declared");
          return;
        }
        await addExternalDep.mutateAsync({
          serviceId,
          name,
          description: externalDescription.trim(),
        });
      }
      resetForm();
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add dependency");
    }
  }

  async function removeDep(dep: ServiceDependency) {
    const ok = await confirm({
      title: `Remove dependency on '${dep.to_service_name}'?`,
      message:
        dep.kind === "external"
          ? "The external dependency record will be deleted."
          : "The edge will be deleted; the services themselves stay intact.",
      confirmLabel: "Remove",
      variant: "danger",
    });
    if (!ok) return;
    if (dep.kind === "service" && dep.to_service_id) {
      await deleteCatalogDep.mutateAsync({
        serviceId,
        toServiceId: dep.to_service_id,
      });
    } else {
      await deleteExternalDep.mutateAsync({
        serviceId,
        name: dep.to_service_name,
      });
    }
  }

  const adding = addCatalogDep.isPending || addExternalDep.isPending;

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
            setShowForm((v) => {
              if (v) resetForm();
              return !v;
            });
          }}
        >
          {showForm ? "Cancel" : "Add dependency"}
        </Button>
      </div>

      {showForm && (
        <div className="space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4">
          <KindToggle kind={kind} onChange={setKind} />

          {kind === "service" ? (
            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                This service depends on
              </label>
              {graph.isLoading ? (
                <Skeleton className="h-9 w-full" />
              ) : comboboxOptions.length === 0 ? (
                <p className="text-[12px] text-zinc-500 dark:text-zinc-400">
                  No other services declared yet. Use the External tab to add
                  a target outside the catalog.
                </p>
              ) : (
                <Combobox
                  value={selectedServiceId}
                  onChange={setSelectedServiceId}
                  options={comboboxOptions}
                  placeholder="Search services…"
                  emptyMessage="No service matches that name."
                />
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <Input
                label="Name *"
                placeholder="e.g. Stripe API"
                value={externalName}
                onChange={(e) => setExternalName(e.target.value)}
                autoFocus
              />
              <Textarea
                label="Description"
                placeholder="What does this service rely on it for?"
                value={externalDescription}
                onChange={(e) => setExternalDescription(e.target.value)}
                rows={2}
              />
            </div>
          )}

          {error && (
            <p className="text-[11px] text-rose-600 dark:text-rose-400">{error}</p>
          )}

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              loading={adding}
              disabled={
                kind === "service"
                  ? !selectedServiceId || comboboxOptions.length === 0
                  : !externalName.trim()
              }
              onClick={submit}
            >
              Add
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                resetForm();
                setShowForm(false);
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
          No dependencies declared yet. Click "Add dependency" to connect this
          service to another one (catalog or external).
        </p>
      ) : (
        <div className="space-y-0">
          {depList.map((dep) => (
            <DependencyRow
              key={`${dep.kind}-${dep.to_service_id ?? dep.to_service_name}`}
              dep={dep}
              onRemove={() => removeDep(dep)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function KindToggle({
  kind,
  onChange,
}: {
  kind: FormKind;
  onChange: (k: FormKind) => void;
}) {
  return (
    <div className="inline-flex items-center rounded-lg border border-zinc-200 dark:border-zinc-700/50 p-0.5 text-[11px]">
      {(
        [
          { value: "service", label: "Catalog service" },
          { value: "external", label: "External" },
        ] as const
      ).map((opt) => {
        const active = kind === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`px-2.5 py-1 rounded-md transition-colors ${
              active
                ? "bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)] text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]"
                : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function DependencyRow({
  dep,
  onRemove,
}: {
  dep: ServiceDependency;
  onRemove: () => void;
}) {
  const isExternal = dep.kind === "external";
  const Icon = isExternal ? ExternalLink : Boxes;
  return (
    <div className="flex items-center justify-between py-2.5 -mx-2 px-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group">
      <div className="flex items-center gap-2 min-w-0">
        <Icon className="w-4 h-4 text-zinc-400 dark:text-zinc-500 flex-shrink-0" />
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
              {dep.to_service_name}
            </span>
            {dep.team_name && (
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500 inline-flex items-center gap-1">
                <Users className="w-3 h-3" /> {dep.team_name}
              </span>
            )}
            {isExternal && (
              <span className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 border border-zinc-200 dark:border-zinc-700/50 rounded px-1 py-0.5">
                external
              </span>
            )}
          </div>
          {isExternal && dep.description && (
            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5">
              {dep.description}
            </p>
          )}
        </div>
      </div>
      <button
        onClick={onRemove}
        // Hover-only visibility hid the action from keyboard-only users.
        // ``focus:opacity-100`` brings the button back as soon as it
        // takes focus (programmatic, screen-reader, or keyboard tab).
        // ``group-focus-within`` covers the case where focus is on
        // another descendant of the row. The aria-label names the
        // dependency so a screen-reader user can disambiguate among
        // rows in the list.
        className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus:opacity-100 text-zinc-400 hover:text-rose-500 focus-visible:text-rose-500 transition-opacity p-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/50"
        aria-label={`Remove dependency on ${dep.to_service_name}`}
      >
        <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
