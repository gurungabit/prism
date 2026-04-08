import type { ReactNode } from "react";

type BadgeVariant = "success" | "warning" | "danger" | "info" | "neutral" | "accent";
type BadgeSize = "sm" | "md";

const variantClasses: Record<BadgeVariant, string> = {
  success:
    "bg-emerald-50 text-emerald-700 border-emerald-200/60 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-700/40",
  warning:
    "bg-amber-50 text-amber-700 border-amber-200/60 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-700/40",
  danger:
    "bg-rose-50 text-rose-700 border-rose-200/60 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-700/40",
  info:
    "bg-sky-50 text-sky-700 border-sky-200/60 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-700/40",
  neutral:
    "bg-zinc-100 text-zinc-600 border-zinc-200/60 dark:bg-zinc-800/60 dark:text-zinc-400 dark:border-zinc-600/40",
  accent:
    "bg-[var(--color-accent-muted)] text-[var(--color-accent)] border-[var(--color-accent-subtle)] dark:bg-[var(--color-accent-dark-muted)] dark:text-[var(--color-accent-dark)] dark:border-[var(--color-accent-dark-subtle)]",
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: "text-[10px] px-1.5 py-px",
  md: "text-[11px] px-2 py-0.5",
};

interface BadgeProps {
  variant?: BadgeVariant;
  size?: BadgeSize;
  children: ReactNode;
  className?: string;
}

export function Badge({
  variant = "neutral",
  size = "sm",
  children,
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center font-medium rounded-md border whitespace-nowrap tracking-wide uppercase ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {children}
    </span>
  );
}

export function RiskBadge({ level }: { level: string }) {
  const map: Record<string, BadgeVariant> = {
    low: "success",
    medium: "warning",
    high: "danger",
    critical: "danger",
  };
  return (
    <Badge variant={map[level] || "neutral"} size="md">
      {level}
    </Badge>
  );
}

export function ConfidenceBadge({ score }: { score: number }) {
  const normalized = score > 1 ? score / 100 : score;
  const variant: BadgeVariant =
    normalized >= 0.8 ? "success" : normalized >= 0.5 ? "warning" : "danger";
  return (
    <Badge variant={variant} size="sm">
      {Math.round(normalized * 100)}%
    </Badge>
  );
}

export function ImpactBadge({ impact }: { impact: string }) {
  const map: Record<string, BadgeVariant> = {
    direct: "danger",
    indirect: "warning",
    informational: "info",
    blocking: "danger",
    impacted: "warning",
  };
  return (
    <Badge variant={map[impact] || "neutral"} size="sm">
      {impact}
    </Badge>
  );
}

export function RecommendationBadge({ recommendation }: { recommendation: string }) {
  const lower = recommendation.toLowerCase();
  const variant: BadgeVariant = lower.includes("no-go")
    ? "danger"
    : lower.includes("conditional")
      ? "warning"
      : "success";
  return (
    <Badge variant={variant} size="md">
      {recommendation}
    </Badge>
  );
}
