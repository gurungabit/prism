import { useState, useCallback, useRef, useEffect } from "react";
import { Search } from "lucide-react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  placeholder?: string;
  loading?: boolean;
  initialValue?: string;
}

export function SearchBar({
  onSearch,
  placeholder = "Search the knowledge base...",
  loading = false,
  initialValue = "",
}: SearchBarProps) {
  const [value, setValue] = useState(initialValue);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const inputRef = useRef<HTMLInputElement>(null);

  const debouncedSearch = useCallback(
    (q: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onSearch(q.trim());
      }, 300);
    },
    [onSearch],
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSearch(value.trim());
  }

  return (
    <form onSubmit={handleSubmit} className="relative">
      <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-300 dark:text-zinc-600" />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          debouncedSearch(e.target.value);
        }}
        placeholder={placeholder}
        className="w-full pl-10 pr-4 py-3 rounded-lg border border-zinc-200 dark:border-zinc-600/50 bg-white dark:bg-[#1e1e20] text-[13px] text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-[var(--color-accent)] dark:focus:border-[var(--color-accent-dark)] transition-colors duration-150"
      />
      {loading && (
        <div className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-zinc-200 dark:border-zinc-700 border-t-[var(--color-accent)] dark:border-t-[var(--color-accent-dark)] rounded-full animate-spin" />
      )}
    </form>
  );
}
