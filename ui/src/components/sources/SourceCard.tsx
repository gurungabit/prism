import { useState } from "react";
import { Badge } from "../shared/Badge";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import type { SourceGroup } from "../../lib/api";

interface SourceCardProps {
  source: SourceGroup;
}

const platformLabels: Record<string, string> = {
  gitlab: "GitLab",
  sharepoint: "SharePoint",
  excel: "Excel",
  onenote: "OneNote",
};

export function SourceCard({ source }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);

  const label = platformLabels[source.platform] || source.platform;
  const lastSync = source.last_ingested
    ? new Date(source.last_ingested).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="border-b border-zinc-200/60 dark:border-zinc-700/30 last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full text-left py-3.5 hover:bg-zinc-50/50 dark:hover:bg-zinc-800/20 -mx-2 px-2 rounded-md transition-colors"
      >
        <div className="flex items-center gap-3">
          <FileText className="w-4 h-4 text-zinc-400 dark:text-zinc-500" />
          <div>
            <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100">
              {label}
            </span>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                {source.document_count} documents
              </span>
              {lastSync && (
                <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                  Last sync {lastSync}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="neutral" size="sm">
            {source.platform}
          </Badge>
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-zinc-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />
          )}
        </div>
      </button>

      {expanded && source.documents.length > 0 && (
        <div className="pb-3 pl-7 animate-fade-in-fast">
          <div className="space-y-0.5">
            {source.documents.map((doc) => (
              <div
                key={doc.document_id}
                className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-700/30"
              >
                <div className="flex-1 min-w-0">
                  <span className="text-[12px] font-mono text-zinc-600 dark:text-zinc-400 truncate block">
                    {doc.source_path}
                  </span>
                </div>
                <div className="flex items-center gap-3 ml-3 flex-shrink-0">
                  <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                    {doc.chunk_count} chunks
                  </span>
                  <Badge
                    variant={doc.status === "indexed" ? "success" : "neutral"}
                    size="sm"
                  >
                    {doc.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
