import { useState } from "react";

import { Button } from "../shared/Button";
import { Input } from "../shared/Input";
import { useUpdateOrg } from "../../hooks/useCatalog";

interface OrgFormProps {
  orgId: string;
  initialValues: { name: string };
  onSuccess?: () => void;
  onCancel?: () => void;
}

// Only supports edit today -- the backend doesn't carry a description on
// organizations, and creation lives on the root dashboard rather than a
// detail page. Kept as a parallel component to TeamForm/ServiceForm so the
// catalog editing UX stays shape-consistent.
export function OrgForm({ orgId, initialValues, onSuccess, onCancel }: OrgFormProps) {
  const [name, setName] = useState(initialValues.name);
  const [error, setError] = useState<string | null>(null);
  const updateOrg = useUpdateOrg();

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Org name is required");
      return;
    }
    setError(null);
    try {
      await updateOrg.mutateAsync({ orgId, name: trimmed });
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save org");
    }
  }

  return (
    <form
      className="space-y-3 border border-zinc-200 dark:border-zinc-700/40 rounded-lg p-4"
      onSubmit={submit}
    >
      <Input
        label="Organization name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error ?? undefined}
        autoFocus
      />
      <div className="flex items-center gap-2">
        <Button
          type="submit"
          size="sm"
          loading={updateOrg.isPending}
          disabled={!name.trim() || name.trim() === initialValues.name}
        >
          Save
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
