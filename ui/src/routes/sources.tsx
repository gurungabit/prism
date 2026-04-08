import { useSources, useIngest } from "../hooks/useSources";
import { SourceCard } from "../components/sources/SourceCard";
import { Button } from "../components/shared/Button";
import { EmptyState } from "../components/shared/EmptyState";
import { Skeleton } from "../components/shared/Skeleton";
import { Database, RefreshCw, RotateCcw } from "lucide-react";

export function SourcesPage() {
  const sources = useSources();
  const { ingest, fullIngest } = useIngest();

  const sourceGroups = sources.data?.sources ?? [];

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
            Sources
          </h1>
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            Data platforms connected to your knowledge base.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw className="w-3.5 h-3.5" />}
            loading={ingest.isPending}
            onClick={() => ingest.mutate()}
          >
            Sync
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw className="w-3.5 h-3.5" />}
            loading={fullIngest.isPending}
            onClick={() => fullIngest.mutate()}
          >
            Full Re-index
          </Button>
        </div>
      </div>

      {sources.isLoading ? (
        <div className="space-y-0">
          <div className="py-3.5 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-2">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <div className="py-3.5 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-2">
            <Skeleton className="h-3.5 w-1/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ) : sourceGroups.length > 0 ? (
        <div className="stagger-children">
          {sourceGroups.map((group) => (
            <SourceCard key={group.platform} source={group} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Database className="w-10 h-10" />}
          title="No data sources found"
          description="Run an ingestion to populate your knowledge base from connected platforms."
          action={
            <Button
              size="sm"
              icon={<RefreshCw className="w-3.5 h-3.5" />}
              loading={ingest.isPending}
              onClick={() => ingest.mutate()}
            >
              Run Ingestion
            </Button>
          }
        />
      )}
    </div>
  );
}
