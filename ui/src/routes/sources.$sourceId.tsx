import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { ArrowLeft, CheckCircle2, CircleAlert, Loader2, Plug, RefreshCw, RotateCcw, Trash2 } from "lucide-react";

import { Button } from "../components/shared/Button";
import { Badge } from "../components/shared/Badge";
import { Skeleton } from "../components/shared/Skeleton";
import { EmptyState } from "../components/shared/EmptyState";
import { useConfirm } from "../components/shared/ConfirmDialog";
import {
  useDeclaredSource,
  useDeleteSource,
  useSourceStatus,
  useTriggerIngest,
} from "../hooks/useCatalog";

const kindLabels: Record<string, string> = {
  gitlab: "GitLab",
  sharepoint: "SharePoint",
  excel: "Excel",
  onenote: "OneNote",
};

export function SourceDetailPage() {
  const { sourceId } = useParams({ strict: false }) as { sourceId: string };
  const source = useDeclaredSource(sourceId);
  const status = useSourceStatus(sourceId);
  const triggerIngest = useTriggerIngest();
  const deleteSource = useDeleteSource();
  const navigate = useNavigate();
  const confirm = useConfirm();

  if (source.isLoading) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8 space-y-6">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!source.data) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8">
        <EmptyState
          title="Source not found"
          action={
            <Link to="/sources">
              <Button>Back to sources</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const data = source.data;
  const liveStatus = status.data?.status ?? data.status;
  const isSyncing = liveStatus === "syncing" || liveStatus === "pending";

  const parentLink = data.service_id
    ? ({ to: "/services/$serviceId", params: { serviceId: data.service_id } } as const)
    : data.team_id
      ? ({ to: "/teams/$teamId", params: { teamId: data.team_id } } as const)
      : data.org_id
        ? ({ to: "/orgs/$orgId", params: { orgId: data.org_id } } as const)
        : null;

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </button>
          <div className="flex items-center gap-2 mt-1">
            <Plug className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
            <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
              {data.name}
            </h1>
            <Badge variant="neutral" size="sm">
              {kindLabels[data.kind] ?? data.kind}
            </Badge>
            <StatusBadge status={liveStatus} />
          </div>
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            {data.document_count} documents ingested
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw className="w-3.5 h-3.5" />}
            loading={triggerIngest.isPending && !isSyncing}
            disabled={isSyncing}
            onClick={() => triggerIngest.mutate({ sourceId })}
          >
            Sync now
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw className="w-3.5 h-3.5" />}
            disabled={isSyncing}
            onClick={() => triggerIngest.mutate({ sourceId, force: true })}
          >
            Force re-index
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 className="w-3.5 h-3.5" />}
            onClick={async () => {
              const ok = await confirm({
                title: `Delete source '${data.name}'?`,
                message: "Its documents and chunks will be removed. This can't be undone.",
                confirmLabel: "Delete source",
                variant: "danger",
              });
              if (!ok) return;
              await deleteSource.mutateAsync(sourceId);
              navigate({ to: "/sources" });
            }}
          >
            Delete
          </Button>
        </div>
      </div>

      {data.last_error && (
        <div className="flex items-start gap-2 text-[12px] text-rose-600 dark:text-rose-400 bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200/60 dark:border-rose-700/40 rounded-md p-3">
          <CircleAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-medium">Last run failed</p>
            <p className="mt-0.5 font-mono text-[11px]">{data.last_error}</p>
          </div>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Metadata
        </h2>
        <dl className="space-y-2 text-[12px] text-zinc-600 dark:text-zinc-400">
          <MetaRow label="Scope">
            {parentLink ? (
              <Link
                to={parentLink.to}
                params={parentLink.params}
                className="text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline"
              >
                {data.service_id ? "Service" : data.team_id ? "Team" : "Organization"}
              </Link>
            ) : (
              "—"
            )}
          </MetaRow>
          <MetaRow label="Last ingested">
            {data.last_ingested_at ? new Date(data.last_ingested_at).toLocaleString() : "never"}
          </MetaRow>
          <MetaRow label="Created">{new Date(data.created_at).toLocaleString()}</MetaRow>
          <MetaRow label="Config">
            <pre className="font-mono text-[11px] bg-zinc-50 dark:bg-zinc-800/60 rounded px-2 py-1 overflow-x-auto">
              {JSON.stringify(data.config, null, 2)}
            </pre>
          </MetaRow>
        </dl>
      </section>

      <section className="space-y-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Documents
        </h2>
        {data.documents.length === 0 ? (
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            No documents yet. Hit "Sync now" to kick off the first ingestion.
          </p>
        ) : (
          <div className="space-y-0">
            {data.documents.slice(0, 50).map((doc) => {
              // doc.source_url is populated by the connector (e.g. a GitLab
              // blob URL). Missing for legacy rows ingested before the
              // source_url column was added -- fall back to non-clickable.
              const href = typeof doc.source_url === "string" ? doc.source_url : "";
              const rowClasses =
                "flex items-center justify-between py-2 px-2 -mx-2 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0";

              const rowContent = (
                <>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-mono text-zinc-600 dark:text-zinc-400 truncate">
                      {doc.title || doc.source_path}
                    </p>
                    <p className="text-[11px] text-zinc-400 dark:text-zinc-500 truncate">
                      {doc.source_path}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 ml-3 flex-shrink-0">
                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                      {doc.chunk_count} chunks
                    </span>
                    <Badge variant={doc.status === "indexed" ? "success" : "neutral"} size="sm">
                      {doc.status}
                    </Badge>
                  </div>
                </>
              );

              return href ? (
                <a
                  key={doc.document_id}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${rowClasses} group`}
                  title={`Open ${doc.source_path} in a new tab`}
                >
                  {rowContent}
                </a>
              ) : (
                <div key={doc.document_id} className={rowClasses}>
                  {rowContent}
                </div>
              );
            })}
            {data.documents.length > 50 && (
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500 pt-2">
                …and {data.documents.length - 50} more.
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <dt className="w-28 text-[11px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 pt-0.5">
        {label}
      </dt>
      <dd className="flex-1 text-[12px] text-zinc-700 dark:text-zinc-300">{children}</dd>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ready") {
    return (
      <Badge variant="success" size="sm" className="inline-flex items-center gap-1">
        <CheckCircle2 className="w-3 h-3" />
        ready
      </Badge>
    );
  }
  if (status === "syncing") {
    return (
      <Badge variant="warning" size="sm" className="inline-flex items-center gap-1">
        <Loader2 className="w-3 h-3 animate-spin" />
        syncing
      </Badge>
    );
  }
  if (status === "error") {
    return (
      <Badge variant="danger" size="sm" className="inline-flex items-center gap-1">
        <CircleAlert className="w-3 h-3" />
        error
      </Badge>
    );
  }
  return (
    <Badge variant="neutral" size="sm">
      {status}
    </Badge>
  );
}
