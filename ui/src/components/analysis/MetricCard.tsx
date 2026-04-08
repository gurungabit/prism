import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: ReactNode;
}

export function MetricCard({ label, value, sub, icon }: MetricCardProps) {
  return (
    <div className="flex items-center gap-3 py-2">
      {icon && (
        <span className="text-zinc-300 dark:text-zinc-600">{icon}</span>
      )}
      <div>
        <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          {label}
        </span>
        <div className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 tracking-tight leading-tight">
          {value}
        </div>
        {sub && (
          <span className="text-[11px] text-zinc-400 dark:text-zinc-500">{sub}</span>
        )}
      </div>
    </div>
  );
}
