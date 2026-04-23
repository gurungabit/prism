import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { searchGitlabProjects, type GitLabProject } from "../../lib/api";

interface Props {
  value: string;
  onChange: (path: string) => void;
  label?: string;
  placeholder?: string;
}

const PER_PAGE = 20;

export function GitlabProjectSelect({
  value,
  onChange,
  label = "Project path",
  placeholder = "Search projects…",
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const [debounced, setDebounced] = useState(value);
  const [results, setResults] = useState<GitLabProject[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // The search input is a plain text field; users can always type a path that
  // isn't in the dropdown (e.g. a project the token doesn't have membership to
  // — GitLab's /projects?search=... is token-scoped, but /projects/:path works
  // for any visible project). Keep ``value`` as the source of truth.
  useEffect(() => {
    if (!open) setQuery(value);
  }, [value, open]);

  // Debounce query so we don't fire a request on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  // Reset pagination whenever the search text changes.
  useEffect(() => {
    if (!open) return;
    setPage(1);
    setResults([]);
    setHasMore(false);
  }, [debounced, open]);

  // Fetch page data. The backend falls back to its service-account token
  // when the request omits one, so the UI doesn't need to collect or
  // forward credentials any more.
  useEffect(() => {
    if (!open) return;
    setError(null);
    setLoading(true);
    let cancelled = false;

    searchGitlabProjects({
      q: debounced.trim(),
      page,
      per_page: PER_PAGE,
    })
      .then((data) => {
        if (cancelled) return;
        setResults((prev) => (page === 1 ? data.projects : [...prev, ...data.projects]));
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
  }, [open, debounced, page]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Infinite scroll: load next page when we approach the bottom.
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
    if (results.length === 0 && debounced.trim()) return "No projects found.";
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
              // Keep free-text typing synced with parent state so users can
              // still submit even if they don't pick from the dropdown.
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
              aria-label="Clear project"
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
            {results.map((p) => (
              <button
                key={p.id}
                type="button"
                className="
                  w-full text-left px-3 py-2
                  hover:bg-zinc-100 dark:hover:bg-zinc-800/60
                  focus:outline-none focus:bg-zinc-100 dark:focus:bg-zinc-800/60
                "
                onClick={() => {
                  onChange(p.path_with_namespace);
                  setQuery(p.path_with_namespace);
                  setOpen(false);
                }}
              >
                <div className="text-[13px] text-zinc-900 dark:text-zinc-100 truncate">
                  {p.path_with_namespace}
                </div>
                {p.name && p.name !== p.path_with_namespace && (
                  <div className="text-[11px] text-zinc-500 dark:text-zinc-500 truncate">
                    {p.name}
                  </div>
                )}
              </button>
            ))}
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
