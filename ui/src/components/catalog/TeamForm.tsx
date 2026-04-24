import { useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "../shared/Button";
import { Input, Textarea } from "../shared/Input";
import { useCreateTeam, useUpdateTeam } from "../../hooks/useCatalog";

interface TeamFormProps {
  // ``create`` needs ``orgId``; ``edit`` needs ``teamId`` + ``initialValues``.
  mode: "create" | "edit";
  orgId?: string;
  teamId?: string;
  initialValues?: { name: string; description: string };
  onSuccess?: () => void;
  onCancel?: () => void;
  // ``compact`` = narrow inline row (source wizard). Default = card layout
  // used by the detail pages.
  compact?: boolean;
}

// Single source of truth for creating or editing a team. Used by the
// organization detail page (create + edit team), team detail page (edit
// team), and source creation wizard (create team while picking scope).
export function TeamForm({
  mode,
  orgId,
  teamId,
  initialValues,
  onSuccess,
  onCancel,
  compact = false,
}: TeamFormProps) {
  const [name, setName] = useState(initialValues?.name ?? "");
  const [description, setDescription] = useState(initialValues?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const createTeam = useCreateTeam();
  const updateTeam = useUpdateTeam();
  const pending = mode === "create" ? createTeam.isPending : updateTeam.isPending;

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Team name is required");
      return;
    }
    setError(null);
    try {
      if (mode === "create") {
        if (!orgId) throw new Error("Missing orgId");
        await createTeam.mutateAsync({
          orgId,
          body: { name: trimmed, description: description.trim() },
        });
      } else {
        if (!teamId) throw new Error("Missing teamId");
        await updateTeam.mutateAsync({
          teamId,
          body: { name: trimmed, description: description.trim() },
        });
      }
      setName("");
      setDescription("");
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save team");
    }
  }

  const cardClass = compact
    ? "space-y-2"
    : "space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4";

  return (
    <form className={cardClass} onSubmit={submit}>
      <Input
        label="Team name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error ?? undefined}
        autoFocus
      />
      <Textarea
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={compact ? 2 : 2}
        placeholder="What does this team do?"
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

// Tiny inline-confirm button row used by the source wizard's "+ Add team"
// path. Renders a single Add toggle, then expands to the shared
// ``TeamForm`` (compact variant) so fields stay consistent with the
// detail-page flow.
export function InlineAddTeam({ orgId }: { orgId: string }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-[var(--color-accent)] dark:text-zinc-400 dark:hover:text-[var(--color-accent-dark)]"
      >
        <Plus className="w-3 h-3" />
        Add team
      </button>
    );
  }

  return (
    <div className="w-full">
      <TeamForm
        mode="create"
        orgId={orgId}
        compact
        onSuccess={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}
