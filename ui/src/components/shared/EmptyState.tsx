import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center animate-fade-in">
      {icon && (
        <div className="text-zinc-300 dark:text-zinc-700 mb-5">{icon}</div>
      )}
      <h3 className="text-[13px] font-semibold text-zinc-600 dark:text-zinc-400 mb-1.5 tracking-tight">
        {title}
      </h3>
      {description && (
        <p className="text-[12px] text-zinc-400 dark:text-zinc-500 max-w-xs mb-5 leading-relaxed">
          {description}
        </p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
