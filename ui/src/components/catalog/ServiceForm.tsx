import { useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "../shared/Button";
import { Input, Textarea } from "../shared/Input";
import { useCreateService, useUpdateService } from "../../hooks/useCatalog";

interface ServiceFormProps {
  // ``create`` needs ``teamId``; ``edit`` needs ``serviceId`` + ``initialValues``.
  mode: "create" | "edit";
  teamId?: string;
  serviceId?: string;
  initialValues?: { name: string; repo_url: string; description: string };
  onSuccess?: () => void;
  onCancel?: () => void;
  compact?: boolean;
}

// Single source of truth for creating or editing a service. Shared between
// the team detail page, the service detail page (edit), and the source
// creation wizard (create service while picking scope).
export function ServiceForm({
  mode,
  teamId,
  serviceId,
  initialValues,
  onSuccess,
  onCancel,
  compact = false,
}: ServiceFormProps) {
  const [name, setName] = useState(initialValues?.name ?? "");
  const [repoUrl, setRepoUrl] = useState(initialValues?.repo_url ?? "");
  const [description, setDescription] = useState(initialValues?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const createService = useCreateService();
  const updateService = useUpdateService();
  const pending = mode === "create" ? createService.isPending : updateService.isPending;

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Service name is required");
      return;
    }
    setError(null);
    try {
      if (mode === "create") {
        if (!teamId) throw new Error("Missing teamId");
        await createService.mutateAsync({
          teamId,
          body: {
            name: trimmed,
            repo_url: repoUrl.trim(),
            description: description.trim(),
          },
        });
      } else {
        if (!serviceId) throw new Error("Missing serviceId");
        await updateService.mutateAsync({
          serviceId,
          body: {
            name: trimmed,
            repo_url: repoUrl.trim(),
            description: description.trim(),
          },
        });
      }
      setName("");
      setRepoUrl("");
      setDescription("");
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save service");
    }
  }

  const cardClass = compact
    ? "space-y-2"
    : "space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4";

  return (
    <form className={cardClass} onSubmit={submit}>
      <Input
        label="Service name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error ?? undefined}
        autoFocus
      />
      <Input
        label="Repository URL"
        placeholder="https://gitlab.com/..."
        value={repoUrl}
        onChange={(e) => setRepoUrl(e.target.value)}
      />
      <Textarea
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        placeholder="What does this service do?"
      />
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" loading={pending} disabled={!name.trim()}>
          {mode === "create" ? "Create" : "Save"}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

export function InlineAddService({ teamId }: { teamId: string }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-zinc-500 hover:text-[var(--color-accent)] dark:text-zinc-400 dark:hover:text-[var(--color-accent-dark)]"
      >
        <Plus className="w-3 h-3" />
        Add service
      </button>
    );
  }

  return (
    <div className="w-full px-2 py-1">
      <ServiceForm
        mode="create"
        teamId={teamId}
        compact
        onSuccess={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}
