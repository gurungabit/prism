import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";

export interface ComboboxOption {
  id: string;
  label: string;
  // Optional second-line label rendered under the primary one (e.g. team
  // name under a service, or description under a name).
  hint?: string;
  // Optional grouping. Options sharing the same ``group`` value are
  // visually clustered under the group label.
  group?: string;
  // When true, the option is rendered but not selectable. Used for
  // disambiguating a single-select from already-picked items.
  disabled?: boolean;
}

interface Props {
  value: string | null;
  onChange: (id: string | null) => void;
  options: ComboboxOption[];
  placeholder?: string;
  // Custom empty-state copy when ``options`` is empty *or* no match.
  emptyMessage?: string;
  // Render a Clear button (X) when something's selected. Defaults to true.
  clearable?: boolean;
  // Disable the whole control.
  disabled?: boolean;
  // Layout class overrides. Most callers don't need this.
  className?: string;
}

// Searchable single-select dropdown.
//
// Drop-in replacement for native ``<select>`` when you want type-ahead +
// keyboard nav + group headers. Uses local state and case-insensitive
// substring matching against ``label`` and ``hint``. Keyboard contract:
//
//   - ↓/↑ moves the highlighted option (skips disabled + group headers).
//   - Enter selects the highlighted option and closes the menu.
//   - Esc closes the menu without changing selection.
//
// Visual style mirrors the existing ``GitlabEntitySelect`` so all
// dropdowns in the app feel consistent.
export function Combobox({
  value,
  onChange,
  options,
  placeholder = "Search…",
  emptyMessage = "No matches.",
  clearable = true,
  disabled = false,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Stable IDs for the ARIA wiring. The listbox id is announced by
  // ``aria-controls`` on the input, and ``aria-activedescendant`` points
  // at the currently-highlighted option's id so screen readers can read
  // the option label without focus actually leaving the input.
  const reactId = useId();
  const listboxId = `combobox-listbox-${reactId}`;
  const optionId = (id: string) => `combobox-option-${reactId}-${id}`;

  const selected = useMemo(
    () => options.find((o) => o.id === value) ?? null,
    [options, value],
  );

  // Display either the picked label (when closed) or the user's typing
  // (when open). Clearing the query with a selected value still shows the
  // selected label until the user types.
  const displayValue = open ? query : selected?.label ?? "";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => {
      return (
        o.label.toLowerCase().includes(q) ||
        (o.hint ?? "").toLowerCase().includes(q)
      );
    });
  }, [options, query]);

  // Build (group | option) sequence for rendering and a parallel index
  // map of *just* the selectable option indices for keyboard nav.
  //
  // Disabled rows get ``selectableIndex: null`` so they never share an
  // index with the next enabled row -- without this, a disabled row
  // and the next enabled row both got the current counter value (the
  // counter only ticks on enabled rows), which made the visual
  // highlight light up two siblings at once and disagreed with
  // ``aria-activedescendant``.
  const flat = useMemo(() => {
    const out: (
      | { kind: "group"; label: string }
      | { kind: "option"; option: ComboboxOption; selectableIndex: number | null }
    )[] = [];
    let lastGroup: string | undefined;
    let selectableIndex = 0;
    for (const o of filtered) {
      if (o.group && o.group !== lastGroup) {
        out.push({ kind: "group", label: o.group });
        lastGroup = o.group;
      } else if (!o.group) {
        // Reset so re-introducing a group later still emits its header.
        lastGroup = undefined;
      }
      if (o.disabled) {
        out.push({ kind: "option", option: o, selectableIndex: null });
      } else {
        out.push({ kind: "option", option: o, selectableIndex });
        selectableIndex += 1;
      }
    }
    return out;
  }, [filtered]);

  const selectableOptions = useMemo(
    () => filtered.filter((o) => !o.disabled),
    [filtered],
  );

  // Keep highlight in range when filtered list shrinks.
  useEffect(() => {
    if (highlight >= selectableOptions.length) {
      setHighlight(Math.max(0, selectableOptions.length - 1));
    }
  }, [selectableOptions.length, highlight]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function commit(option: ComboboxOption) {
    if (option.disabled) return;
    onChange(option.id);
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setHighlight((h) => Math.min(h + 1, selectableOptions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = selectableOptions[highlight];
      if (target) commit(target);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <div
        className={`flex items-center gap-2 w-full rounded-lg border px-3 py-2 transition-colors duration-150 ${
          disabled
            ? "border-zinc-200 dark:border-zinc-700/40 bg-zinc-50 dark:bg-zinc-900/40 cursor-not-allowed"
            : "border-zinc-200 dark:border-zinc-600/50 bg-white dark:bg-[#1e1e20] focus-within:border-[var(--color-accent)] dark:focus-within:border-[var(--color-accent-dark)]"
        }`}
      >
        <Search className="w-3.5 h-3.5 text-zinc-400 flex-shrink-0" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          disabled={disabled}
          // ARIA combobox pattern: input is the combobox, dropdown is the
          // listbox referenced by ``aria-controls``, and the highlighted
          // option (focus stays on the input) is named via
          // ``aria-activedescendant`` so screen readers announce it.
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && selectableOptions[highlight]
              ? optionId(selectableOptions[highlight].id)
              : undefined
          }
          className="flex-1 bg-transparent outline-none text-[13px] text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 disabled:cursor-not-allowed"
          placeholder={placeholder}
          value={displayValue}
          onChange={(e) => {
            setQuery(e.target.value);
            setHighlight(0);
            if (!open) setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {clearable && value && !disabled && (
          <button
            type="button"
            className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 flex-shrink-0"
            onClick={() => {
              onChange(null);
              setQuery("");
              inputRef.current?.focus();
            }}
            aria-label="Clear selection"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
        <ChevronDown
          aria-hidden="true"
          className={`w-3.5 h-3.5 text-zinc-400 flex-shrink-0 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </div>

      {open && !disabled && (
        <div
          id={listboxId}
          role="listbox"
          className="
            absolute z-20 mt-1 w-full max-h-64 overflow-y-auto
            rounded-lg border border-zinc-200 dark:border-zinc-700/60
            bg-white dark:bg-[#1e1e20]
            shadow-lg
          "
        >
          {flat.length === 0 ? (
            <div className="px-3 py-2 text-[12px] text-zinc-500 dark:text-zinc-500">
              {emptyMessage}
            </div>
          ) : (
            flat.map((row, i) => {
              if (row.kind === "group") {
                return (
                  <div
                    key={`group-${row.label}-${i}`}
                    role="presentation"
                    className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500"
                  >
                    {row.label}
                  </div>
                );
              }
              // Disabled rows have ``selectableIndex === null`` so the
              // strict-equality check excludes them from highlight.
              const isHighlighted =
                row.selectableIndex !== null &&
                row.selectableIndex === highlight;
              const isSelected = row.option.id === value;
              return (
                <button
                  key={row.option.id}
                  id={optionId(row.option.id)}
                  type="button"
                  // Native ``disabled`` keeps mouse focus management while
                  // the explicit ``aria-disabled`` is what assistive tech
                  // announces.
                  disabled={row.option.disabled}
                  role="option"
                  aria-selected={isSelected}
                  aria-disabled={row.option.disabled || undefined}
                  onMouseEnter={() => {
                    // Skip disabled rows -- moving the highlight onto a
                    // non-selectable target would also desync from
                    // ``aria-activedescendant``.
                    if (row.selectableIndex !== null) {
                      setHighlight(row.selectableIndex);
                    }
                  }}
                  onClick={() => commit(row.option)}
                  className={`
                    w-full text-left px-3 py-2 flex items-start gap-2
                    transition-colors duration-100
                    ${
                      row.option.disabled
                        ? "opacity-40 cursor-not-allowed"
                        : isHighlighted
                          ? "bg-zinc-100 dark:bg-zinc-800/60"
                          : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
                    }
                  `}
                >
                  <Check
                    aria-hidden="true"
                    className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${
                      isSelected
                        ? "text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]"
                        : "opacity-0"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] text-zinc-900 dark:text-zinc-100 truncate">
                      {row.option.label}
                    </div>
                    {row.option.hint && (
                      <div className="text-[11px] text-zinc-500 dark:text-zinc-500 truncate">
                        {row.option.hint}
                      </div>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
