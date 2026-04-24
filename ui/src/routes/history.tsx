import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useHistory, useDeleteAnalysis } from "../hooks/useAnalysis";
import { EmptyState } from "../components/shared/EmptyState";
import { Badge } from "../components/shared/Badge";
import { Modal } from "../components/shared/Modal";
import { Skeleton } from "../components/shared/Skeleton";
import { Button } from "../components/shared/Button";
import { History, FlaskConical, ChevronLeft, ChevronRight, Trash2 } from "lucide-react";

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const statusVariant: Record<string, "success" | "info" | "danger" | "neutral"> = {
  complete: "success",
  completed: "success",
  running: "info",
  failed: "danger",
};

export function HistoryPage() {
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const history = useHistory(limit, offset);
  const deleteAnalysis = useDeleteAnalysis();
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; req: string } | null>(null);

  const threads = history.data?.threads ?? [];
  const total = history.data?.total ?? 0;
  const hasNext = offset + limit < total;
  const hasPrev = offset > 0;

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-8">
      <div>
        <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
          History
        </h1>
        <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
          Past analysis runs and their results.
        </p>
      </div>

      {history.isLoading ? (
        <div className="space-y-0">
          <div className="py-3 border-b border-zinc-100 dark:border-zinc-800/30 space-y-2">
            <Skeleton className="h-3.5 w-3/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <div className="py-3 border-b border-zinc-100 dark:border-zinc-800/30 space-y-2">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-1/5" />
          </div>
          <div className="py-3 space-y-2">
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ) : threads.length > 0 ? (
        <>
          <div className="space-y-0">
            {threads.map((thread) => (
              <Link
                key={thread.thread_id}
                to="/analyze/$runId"
                params={{ runId: thread.thread_id }}
                className="flex items-center justify-between py-3 border-b border-zinc-100 dark:border-zinc-800/30 last:border-0 hover:bg-zinc-50/50 dark:hover:bg-zinc-800/20 -mx-2 px-2 rounded-md transition-colors group"
              >
                <div className="flex-1 min-w-0 mr-4">
                  <p
                    className="text-[13px] text-zinc-800 dark:text-zinc-200 truncate group-hover:text-[var(--color-accent)] dark:group-hover:text-[var(--color-accent-dark)] transition-colors"
                    title={thread.requirement}
                  >
                    {thread.title || thread.requirement}
                  </p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                      {timeAgo(thread.last_turn_at)}
                    </span>
                    {thread.turn_count > 1 && (
                      <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                        {thread.turn_count} turns
                      </span>
                    )}
                    {thread.duration_seconds != null && (
                      <span className="text-[11px] font-mono text-zinc-400 dark:text-zinc-500">
                        {thread.duration_seconds < 60
                          ? `${Math.round(thread.duration_seconds)}s`
                          : thread.duration_seconds < 3600
                            ? `${Math.floor(thread.duration_seconds / 60)}m ${Math.round(thread.duration_seconds % 60)}s`
                            : `${Math.floor(thread.duration_seconds / 3600)}h ${Math.floor((thread.duration_seconds % 3600) / 60)}m`}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <Badge
                    variant={statusVariant[thread.status] || "neutral"}
                    size="sm"
                  >
                    {thread.status}
                  </Badge>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDeleteTarget({ id: thread.thread_id, req: thread.requirement });
                    }}
                    className="p-1.5 rounded-lg text-zinc-300 dark:text-zinc-600 hover:text-rose-500 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </Link>
            ))}
          </div>

          {(hasPrev || hasNext) && (
            <div className="flex items-center justify-between pt-2">
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                {offset + 1}–{Math.min(offset + limit, total)} of {total}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={!hasPrev}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700/30 disabled:opacity-30 disabled:pointer-events-none transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setOffset(offset + limit)}
                  disabled={!hasNext}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700/30 disabled:opacity-30 disabled:pointer-events-none transition-colors"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <EmptyState
          icon={<History className="w-10 h-10" />}
          title="No analysis history"
          description="Run your first analysis to see results here."
          action={
            <Link to="/analyze">
              <Button size="sm" icon={<FlaskConical className="w-3.5 h-3.5" />}>
                New Analysis
              </Button>
            </Link>
          }
        />
      )}

      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="Delete analysis"
        width="max-w-sm"
      >
        <p className="text-[13px] text-zinc-600 dark:text-zinc-400 leading-relaxed">
          <span className="font-medium text-zinc-800 dark:text-zinc-200">{deleteTarget?.req}</span>
          {" "}will be permanently deleted.
        </p>
        <div className="flex items-center justify-end gap-2 mt-5">
          <Button variant="ghost" size="sm" onClick={() => setDeleteTarget(null)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={() => {
              if (deleteTarget) deleteAnalysis.mutate(deleteTarget.id);
              setDeleteTarget(null);
            }}
            className="!bg-red-500/90 !text-white hover:!bg-red-600"
          >
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}
