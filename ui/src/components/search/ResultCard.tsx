import type { SearchResult } from "../../lib/schemas";
import { Badge } from "../shared/Badge";
import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";

function highlightText(text: string, query: string): ReactNode {
  if (!query.trim()) return text;

  const words = query
    .trim()
    .split(/\s+/)
    .filter((w) => w.length > 1);
  if (words.length === 0) return text;

  const escaped = words.map((w) =>
    w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
  );
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);

  if (parts.length === 1) return text;

  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark
            key={i}
            className="bg-amber-200/70 dark:bg-amber-500/25 text-inherit rounded-sm px-px"
          >
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

interface ResultCardProps {
  result: SearchResult;
  query?: string;
}

export function ResultCard({ result, query = "" }: ResultCardProps) {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(result.score * 100);
  const barWidth = pct;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => setExpanded(!expanded)}
      onKeyDown={(e) => e.key === "Enter" && setExpanded(!expanded)}
      className="py-3 border-b border-zinc-100 dark:border-zinc-800/30 last:border-0 cursor-pointer hover:bg-zinc-50/50 dark:hover:bg-zinc-800/20 -mx-2 px-2 rounded-md transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            {expanded ? (
              <ChevronDown className="w-3 h-3 text-zinc-400 flex-shrink-0" />
            ) : (
              <ChevronRight className="w-3 h-3 text-zinc-400 flex-shrink-0" />
            )}
            <h4 className="text-[13px] font-medium text-zinc-800 dark:text-zinc-200 truncate">
              {highlightText(result.document_title || result.source_path.split("/").pop() || "", query)}
            </h4>
            <Badge variant="neutral" size="sm">
              {result.platform}
            </Badge>
          </div>

          <p className="text-[11px] text-zinc-400 dark:text-zinc-500 line-clamp-2 ml-5">
            {highlightText(result.content, query)}
          </p>
        </div>

        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500">
            {pct}%
          </span>
          <div className="w-10 h-1 bg-zinc-100 dark:bg-zinc-700/50 rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--color-accent)] dark:bg-[var(--color-accent-dark)] rounded-full"
              style={{ width: `${barWidth}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 mt-1.5 ml-5">
        <Badge variant="neutral" size="sm">
          {result.doc_type}
        </Badge>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-zinc-100 dark:border-zinc-700/40 ml-5 animate-fade-in-fast">
          <p className="text-[12px] text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap mb-3">
            {highlightText(result.content, query)}
          </p>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500 truncate">
              {result.source_path}
            </span>
            <ExternalLink className="w-3 h-3 text-zinc-300 dark:text-zinc-600" />
          </div>
        </div>
      )}
    </div>
  );
}
