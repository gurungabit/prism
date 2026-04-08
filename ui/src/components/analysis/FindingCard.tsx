import type { z } from "zod";
import type { RiskItemSchema } from "../../lib/schemas";
import { FileText } from "lucide-react";

type RiskItem = z.infer<typeof RiskItemSchema>;

interface FindingCardProps {
  finding: RiskItem;
}

const levelColors: Record<string, string> = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-rose-500",
  critical: "bg-rose-600",
};

export function FindingCard({ finding }: FindingCardProps) {
  const categoryLabel = finding.category.replace(/_/g, " ");
  const dotColor = levelColors[finding.level] || "bg-zinc-400";

  return (
    <div className="flex items-start gap-3 py-3 border-b border-zinc-100 dark:border-zinc-800/30 last:border-0">
      <div
        className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${dotColor}`}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-medium text-zinc-700 dark:text-zinc-300 capitalize">
            {categoryLabel}
          </span>
          <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            {finding.level}
          </span>
        </div>
        <p className="text-[12px] text-zinc-500 dark:text-zinc-400 mt-0.5">
          {finding.description}
        </p>
        {finding.mitigation && (
          <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-1 italic">
            Mitigation: {finding.mitigation}
          </p>
        )}
        {finding.sources.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {finding.sources.map((s, i) => (
              <div key={i} className="flex items-start gap-1.5">
                <FileText className="w-3 h-3 text-zinc-400 dark:text-zinc-500 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <span
                    className="text-[11px] font-mono text-zinc-500 dark:text-zinc-400 break-all"
                    title={s.document_path}
                  >
                    {s.document_path.length > 60
                      ? s.document_path.slice(0, 57) + "\u2026"
                      : s.document_path}
                  </span>
                  {s.excerpt && (
                    <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5 italic leading-relaxed">
                      &ldquo;{s.excerpt}&rdquo;
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
