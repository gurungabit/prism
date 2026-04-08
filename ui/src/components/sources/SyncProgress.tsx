interface SyncProgressProps {
  progress: number;
  label?: string;
}

export function SyncProgress({ progress, label }: SyncProgressProps) {
  return (
    <div className="space-y-1.5">
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
            {label}
          </span>
          <span className="text-[11px] font-mono text-zinc-400 dark:text-zinc-500">
            {Math.round(progress)}%
          </span>
        </div>
      )}
      <div className="w-full h-1 bg-zinc-100 dark:bg-zinc-700/50 rounded-full overflow-hidden">
        <div
          className="h-full bg-[var(--color-accent)] dark:bg-[var(--color-accent-dark)] rounded-full transition-[width] duration-300 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}
