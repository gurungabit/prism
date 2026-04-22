import { Link } from "@tanstack/react-router";
import { Badge } from "../shared/Badge";
import { CheckCircle2, CircleAlert, Loader2, Plug } from "lucide-react";
import type { DeclaredSource, SourceStatus } from "../../lib/api";

interface DeclaredSourceRowProps {
  source: DeclaredSource;
}

const kindLabels: Record<string, string> = {
  gitlab: "GitLab",
  sharepoint: "SharePoint",
  excel: "Excel",
  onenote: "OneNote",
};

const statusVariant: Record<SourceStatus, "success" | "warning" | "danger" | "neutral"> = {
  ready: "success",
  syncing: "warning",
  pending: "neutral",
  error: "danger",
};

const statusIcon: Record<SourceStatus, React.ReactNode> = {
  ready: <CheckCircle2 className="w-3 h-3" />,
  syncing: <Loader2 className="w-3 h-3 animate-spin" />,
  pending: <Plug className="w-3 h-3" />,
  error: <CircleAlert className="w-3 h-3" />,
};

function formatScope(source: DeclaredSource): string {
  if (source.service_id) return "service";
  if (source.team_id) return "team";
  if (source.org_id) return "org";
  return "—";
}

function formatLastSync(ts: string | null): string {
  if (!ts) return "never";
  const date = new Date(ts);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DeclaredSourceRow({ source }: DeclaredSourceRowProps) {
  const kindLabel = kindLabels[source.kind] ?? source.kind;

  return (
    <Link
      to="/sources/$sourceId"
      params={{ sourceId: source.id }}
      className="flex items-center justify-between py-3 -mx-2 px-2 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/30 border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0 group"
    >
      <div className="flex items-center gap-3 min-w-0">
        <Plug className="w-4 h-4 text-zinc-400 dark:text-zinc-500 flex-shrink-0" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 truncate">
              {source.name}
            </span>
            <Badge variant="neutral" size="sm">
              {kindLabel}
            </Badge>
            <Badge variant="info" size="sm">
              {formatScope(source)}
            </Badge>
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-[11px] text-zinc-400 dark:text-zinc-500">
            <span>{source.document_count ?? 0} docs</span>
            <span>·</span>
            <span>last sync {formatLastSync(source.last_ingested_at)}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        <Badge variant={statusVariant[source.status]} size="sm" className="inline-flex items-center gap-1">
          <span className="flex items-center">{statusIcon[source.status]}</span>
          <span>{source.status}</span>
        </Badge>
      </div>
    </Link>
  );
}
