// Browse-side filters for the search page. Type-by-doc-type was retired
// because the backend's path-regex detection produced ``unknown`` for
// most chunks; the chips ended up either empty (selecting a known type
// hid most of the corpus) or noisy (``unknown`` dominated). The two
// filters here pull more weight in practice: recency keeps the LLM off
// stale runbooks, and platform is the obvious distinction when the
// catalog mixes GitLab repos with SharePoint / Excel / OneNote stubs.

export type Recency = "" | "30d" | "6mo" | "1y";

const RECENCY_OPTIONS: { value: Recency; label: string }[] = [
  { value: "", label: "Any time" },
  { value: "30d", label: "Last 30 days" },
  { value: "6mo", label: "Last 6 months" },
  { value: "1y", label: "Last year" },
];

const PLATFORM_OPTIONS = ["gitlab", "sharepoint", "excel", "onenote"] as const;
type Platform = (typeof PLATFORM_OPTIONS)[number];

interface FilterChipsProps {
  platforms: string[];
  recency: Recency;
  onChange: (next: { platforms: string[]; recency: Recency }) => void;
}

function chipClass(active: boolean): string {
  const base =
    "text-[11px] px-2 py-0.5 rounded-md border transition-all duration-150";
  if (active) {
    return (
      `${base} bg-[var(--color-accent)] border-[var(--color-accent)] text-white ` +
      `dark:bg-[var(--color-accent-dark)] dark:border-[var(--color-accent-dark)] dark:text-zinc-900`
    );
  }
  return (
    `${base} bg-transparent border-zinc-200 dark:border-zinc-600/50 ` +
    `text-zinc-500 dark:text-zinc-400 hover:border-zinc-300 dark:hover:border-zinc-500/60`
  );
}

export function FilterChips({ platforms, recency, onChange }: FilterChipsProps) {
  function togglePlatform(value: Platform) {
    const next = platforms.includes(value)
      ? platforms.filter((p) => p !== value)
      : [...platforms, value];
    onChange({ platforms: next, recency });
  }

  function selectRecency(value: Recency) {
    onChange({ platforms, recency: value });
  }

  return (
    <div className="flex flex-wrap gap-3">
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Platform
        </span>
        {PLATFORM_OPTIONS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => togglePlatform(p)}
            className={chipClass(platforms.includes(p))}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Modified
        </span>
        {RECENCY_OPTIONS.map((opt) => (
          <button
            key={opt.value || "any"}
            type="button"
            onClick={() => selectRecency(opt.value)}
            className={chipClass(recency === opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
