import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  compact?: boolean;
  className?: string;
  onClick?: () => void;
  hoverable?: boolean;
}

export function Card({
  children,
  compact = false,
  className = "",
  onClick,
  hoverable = false,
}: CardProps) {
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
      className={`
        rounded-lg border border-zinc-200/80 dark:border-zinc-700/40
        bg-white dark:bg-[#1e1e20]
        ${compact ? "p-4" : "p-5"}
        ${hoverable ? "transition-all duration-150 hover:border-zinc-300 dark:hover:border-zinc-600/60 cursor-pointer" : ""}
        ${onClick ? "cursor-pointer" : ""}
        ${className}
      `}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-center justify-between mb-3 ${className}`}>
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h3 className={`text-[13px] font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 ${className}`}>
      {children}
    </h3>
  );
}
