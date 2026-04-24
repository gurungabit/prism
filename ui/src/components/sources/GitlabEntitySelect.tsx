import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";

interface Props<T> {
  value: string;
  onChange: (path: string) => void;
  // Fetches a page of results given the current query + pagination.
  fetcher: (args: { q: string; page: number; per_page: number }) => Promise<{
    items: T[];
    has_more: boolean;
  }>;
  // Extracts the canonical path (stored in the parent's form state) from a
  // result -- e.g. ``path_with_namespace`` for projects, ``full_path`` for
  // groups.
  getPath: (item: T) => string;
  // Secondary display label shown under the path when different.
  getLabel: (item: T) => string;
  // Stable id for React list keys.
  getId: (item: T) => number | string;
  label?: string;
  placeholder?: string;
}

const PER_PAGE = 20;

// Generic searchable dropdown shared between the project picker and the
// group picker. The GitLab API returns different entity shapes per
// endpoint, so the parent supplies ``fetcher`` + accessors instead of this
// component hard-coding either one.
export function GitlabEntitySelect<T>({
  value,
  onChange,
  fetcher,
  getPath,
  getLabel,
  getId,
  label = "Path",
  placeholder = "Search…",
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const [debounced, setDebounced] = useState(value);
  const [results, setResults] = useState<T[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Free-text typing still works (backend accepts any path the token can
  // resolve). Keep ``value`` as the source of truth.
  useEffect(() => {
    if (!open) setQuery(value);
  }, [value, open]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    setPage(1);
    setResults([]);
    setHasMore(false);
  }, [debounced, open]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setLoading(true);
    let cancelled = false;

    fetcher({
      q: debounced.trim(),
      page,
      per_page: PER_PAGE,
    })
      .then((data) => {
        if (cancelled) return;
        setResults((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setHasMore(data.has_more);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message || "Search failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, debounced, page, fetcher]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const onScroll = () => {
    const el = listRef.current;
    if (!el || loading || !hasMore) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
      setPage((p) => p + 1);
    }
  };

  const showDropdown = open && (loading || results.length > 0 || error);

  const helperText = useMemo(() => {
    if (loading && results.length === 0) return "Searching…";
    if (error) return error;
    if (results.length === 0 && debounced.trim()) return "No matches found.";
    return null;
  }, [loading, results.length, error, debounced]);

  return (
    <div className="space-y-1.5" ref={containerRef}>
      {label && (
        <label className="block text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          {label}
        </label>
      )}
      <div className="relative">
        <div
          className="
            flex items-center gap-2
            w-full rounded-lg border border-zinc-200 dark:border-zinc-600/50
            bg-white dark:bg-[#1e1e20]
            px-3 py-2
            focus-within:border-[var(--color-accent)] dark:focus-within:border-[var(--color-accent-dark)]
            transition-colors duration-150
          "
        >
          <Search className="w-3.5 h-3.5 text-zinc-400" />
          <input
            type="text"
            className="
              flex-1 bg-transparent outline-none
              text-[13px] text-zinc-900 dark:text-zinc-100
              placeholder:text-zinc-400 dark:placeholder:text-zinc-600
            "
            placeholder={placeholder}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onChange(e.target.value);
            }}
            onFocus={() => setOpen(true)}
          />
          {value && (
            <button
              type="button"
              className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
              onClick={() => {
                setQuery("");
                onChange("");
                setOpen(true);
              }}
              aria-label="Clear"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-400" />}
        </div>

        {showDropdown && (
          <div
            ref={listRef}
            onScroll={onScroll}
            className="
              absolute z-20 mt-1 w-full max-h-64 overflow-y-auto
              rounded-lg border border-zinc-200 dark:border-zinc-700/60
              bg-white dark:bg-[#1e1e20]
              shadow-lg
            "
          >
            {error && (
              <div className="px-3 py-2 text-[12px] text-rose-600 dark:text-rose-400">
                {error}
              </div>
            )}
            {results.map((item) => {
              const path = getPath(item);
              const labelText = getLabel(item);
              return (
                <button
                  key={getId(item)}
                  type="button"
                  className="
                    w-full text-left px-3 py-2
                    hover:bg-zinc-100 dark:hover:bg-zinc-800/60
                    focus:outline-none focus:bg-zinc-100 dark:focus:bg-zinc-800/60
                  "
                  onClick={() => {
                    onChange(path);
                    setQuery(path);
                    setOpen(false);
                  }}
                >
                  <div className="text-[13px] text-zinc-900 dark:text-zinc-100 truncate">
                    {path}
                  </div>
                  {labelText && labelText !== path && (
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-500 truncate">
                      {labelText}
                    </div>
                  )}
                </button>
              );
            })}
            {loading && results.length > 0 && (
              <div className="px-3 py-2 text-[11px] text-zinc-500 dark:text-zinc-500 flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin" />
                Loading more…
              </div>
            )}
            {!loading && !hasMore && results.length > 0 && (
              <div className="px-3 py-2 text-[11px] text-zinc-500 dark:text-zinc-500">
                End of results.
              </div>
            )}
          </div>
        )}
      </div>
      {helperText && !showDropdown && (
        <p className="text-[11px] text-zinc-500 dark:text-zinc-500">{helperText}</p>
      )}
    </div>
  );
}
