interface FilterChipsProps {
  filters: {
    entityTypes: string[];
    teams: string[];
    services: string[];
  };
  selected: Record<string, string[]>;
  onChange: (selected: Record<string, string[]>) => void;
}

function ChipGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  if (options.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
        {label}
      </span>
      {options.map((opt) => {
        const active = selected.includes(opt);
        return (
          <button
            key={opt}
            onClick={() => onToggle(opt)}
            className={`
              text-[11px] px-2 py-0.5 rounded-md border transition-all duration-150
              ${
                active
                  ? "bg-[var(--color-accent)] border-[var(--color-accent)] text-white dark:bg-[var(--color-accent-dark)] dark:border-[var(--color-accent-dark)] dark:text-zinc-900"
                  : "bg-transparent border-zinc-200 dark:border-zinc-600/50 text-zinc-500 dark:text-zinc-400 hover:border-zinc-300 dark:hover:border-zinc-500/60"
              }
            `}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}

export function FilterChips({ filters, selected, onChange }: FilterChipsProps) {
  function toggle(group: string, value: string) {
    const current = selected[group] || [];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange({ ...selected, [group]: next });
  }

  return (
    <div className="flex flex-wrap gap-3">
      <ChipGroup
        label="Type"
        options={filters.entityTypes}
        selected={selected["entityTypes"] || []}
        onToggle={(v) => toggle("entityTypes", v)}
      />
      <ChipGroup
        label="Team"
        options={filters.teams}
        selected={selected["teams"] || []}
        onToggle={(v) => toggle("teams", v)}
      />
      <ChipGroup
        label="Service"
        options={filters.services}
        selected={selected["services"] || []}
        onToggle={(v) => toggle("services", v)}
      />
    </div>
  );
}
