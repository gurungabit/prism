import { useEffect } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useSearchMutation } from "../hooks/useSearch";
import { SearchBar } from "../components/search/SearchBar";
import { FilterChips } from "../components/search/FilterChips";
import { ResultCard } from "../components/search/ResultCard";
import { EmptyState } from "../components/shared/EmptyState";
import { Skeleton } from "../components/shared/Skeleton";
import { Search } from "lucide-react";
import { Button } from "../components/shared/Button";

const SEARCH_PAGE_SIZE = 40;

function buildPageWindow(currentPage: number, hasMore: boolean) {
  const pages = [currentPage];
  if (currentPage > 2) pages.unshift(currentPage - 2);
  if (currentPage > 1) pages.unshift(currentPage - 1);
  if (hasMore) pages.push(currentPage + 1);
  return Array.from(new Set(pages)).filter((page) => page > 0);
}

function buildKnownPageWindow(currentPage: number, totalPages: number) {
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  const pages: number[] = [];
  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }
  return pages;
}

export function SearchPage() {
  const navigate = useNavigate({ from: "/search" });
  const searchState = useSearch({ from: "/search" });
  const search = useSearchMutation();

  const selectedFilters: Record<string, string[]> = {
    entityTypes: searchState.entityTypes,
    teams: searchState.teams,
    services: searchState.services,
  };

  function updateRouteSearch(
    next: {
      q?: string;
      page?: number;
      entityTypes?: string[];
      teams?: string[];
      services?: string[];
    },
    replace = false,
  ) {
    void navigate({
      to: "/search",
      replace,
      search: {
        q: next.q?.trim() ? next.q.trim() : undefined,
        page: next.q?.trim() ? Math.max(next.page ?? 1, 1) : undefined,
        entityTypes: next.entityTypes?.length ? next.entityTypes : undefined,
        teams: next.teams?.length ? next.teams : undefined,
        services: next.services?.length ? next.services : undefined,
      },
    });
  }

  function performSearch(nextQuery: string, nextPage = 1) {
    const apiFilters: Record<string, unknown> = {};
    if (selectedFilters["entityTypes"]?.length) apiFilters["doc_type"] = selectedFilters["entityTypes"];
    if (selectedFilters["teams"]?.length) apiFilters["team_hint"] = selectedFilters["teams"];
    if (selectedFilters["services"]?.length) apiFilters["service_hint"] = selectedFilters["services"];

    search.mutate({
      query: nextQuery,
      filters: apiFilters,
      page: nextPage,
      page_size: SEARCH_PAGE_SIZE,
    });
  }

  function handleSearch(nextQuery: string) {
    updateRouteSearch(
      {
        q: nextQuery,
        page: 1,
        entityTypes: selectedFilters.entityTypes,
        teams: selectedFilters.teams,
        services: selectedFilters.services,
      },
      true,
    );
  }

  function handlePageChange(nextPage: number) {
    if (!searchState.q.trim() || nextPage < 1) return;
    updateRouteSearch(
      {
        q: searchState.q,
        page: nextPage,
        entityTypes: selectedFilters.entityTypes,
        teams: selectedFilters.teams,
        services: selectedFilters.services,
      },
      false,
    );
  }

  useEffect(() => {
    const trimmedQuery = searchState.q.trim();
    if (!trimmedQuery) {
      search.reset();
      return;
    }
    performSearch(trimmedQuery, searchState.page);
    // Route search state is the source of truth for search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    searchState.q,
    searchState.page,
    searchState.entityTypes,
    searchState.teams,
    searchState.services,
  ]);

  function handleFilterChange(nextSelected: Record<string, string[]>) {
    updateRouteSearch(
      {
        q: searchState.q,
        page: 1,
        entityTypes: nextSelected.entityTypes ?? [],
        teams: nextSelected.teams ?? [],
        services: nextSelected.services ?? [],
      },
      false,
    );
  }

  const pageStart = search.data ? (search.data.page - 1) * search.data.page_size + 1 : 0;
  const pageEnd = search.data ? pageStart + search.data.results.length - 1 : 0;
  const totalPages = search.data?.total != null
    ? Math.max(1, Math.ceil(search.data.total / search.data.page_size))
    : null;
  const pageWindow = search.data
    ? totalPages
      ? buildKnownPageWindow(search.data.page, totalPages)
      : buildPageWindow(search.data.page, search.data.has_more)
    : [];
  const resultsSummary = !search.data
    ? ""
    : search.data.results.length === 0
    ? `No results for “${search.data.query}”`
    : search.data.total !== null
    ? `Showing ${pageStart}-${pageEnd} of ${search.data.total} results for “${search.data.query}”`
    : `Showing ${pageStart}-${pageEnd} results for “${search.data.query}”`;

  function renderPager() {
    if (!search.data || search.data.results.length === 0) return null;
    const currentPage = search.data.page;
    const firstPage = pageWindow[0] ?? 1;
    const lastPageInWindow = pageWindow[pageWindow.length - 1] ?? currentPage;

    return (
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={search.isPending || currentPage <= 1}
          onClick={() => handlePageChange(currentPage - 1)}
        >
          Previous
        </Button>
        <div className="flex items-center gap-1">
          {firstPage > 1 && (
            <>
              <Button
                variant="ghost"
                size="sm"
                disabled={search.isPending}
                onClick={() => handlePageChange(1)}
                className="min-w-8 px-2"
              >
                1
              </Button>
              {firstPage > 2 && (
                <span className="px-1 text-[11px] text-zinc-400 dark:text-zinc-500">
                  ...
                </span>
              )}
            </>
          )}

          {pageWindow.map((pageNumber) => (
            <Button
              key={pageNumber}
              variant={pageNumber === currentPage ? "accent" : "ghost"}
              size="sm"
              disabled={search.isPending}
              onClick={() => handlePageChange(pageNumber)}
              className="min-w-8 px-2"
            >
              {pageNumber}
            </Button>
          ))}
          {totalPages && lastPageInWindow < totalPages && (
            <>
              {lastPageInWindow < totalPages - 1 && (
                <span className="px-1 text-[11px] text-zinc-400 dark:text-zinc-500">
                  ...
                </span>
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={search.isPending}
                onClick={() => handlePageChange(totalPages)}
                className="min-w-8 px-2"
              >
                {totalPages}
              </Button>
            </>
          )}
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={search.isPending || (totalPages ? currentPage >= totalPages : !search.data.has_more)}
          onClick={() => handlePageChange(currentPage + 1)}
        >
          Next
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
          Search
        </h1>
        <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
          Search across your entire knowledge base with hybrid retrieval.
        </p>
      </div>

      <SearchBar
        onSearch={handleSearch}
        loading={search.isPending}
        initialValue={searchState.q}
      />


      <FilterChips
        filters={{
          entityTypes: ["wiki", "issue", "merge_request", "pipeline", "readme"],
          teams: [],
          services: [],
        }}
        selected={selectedFilters}
        onChange={handleFilterChange}
      />

      <div>
        {search.isPending ? (
          <div className="space-y-0">
            <div className="py-3 border-b border-zinc-100 dark:border-zinc-800/30 space-y-2">
              <Skeleton className="h-3.5 w-2/5" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-3/4" />
            </div>
            <div className="py-3 border-b border-zinc-100 dark:border-zinc-800/30 space-y-2">
              <Skeleton className="h-3.5 w-1/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
            <div className="py-3 space-y-2">
              <Skeleton className="h-3.5 w-2/5" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-3/4" />
            </div>
          </div>
        ) : search.data ? (
          <>
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
                {resultsSummary}
              </p>
              {renderPager()}
            </div>
            {search.data.results.length > 0 ? (
              <div className="stagger-children">
                {search.data.results.map((r) => (
                  <ResultCard key={r.chunk_id} result={r} query={search.data.query} />
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<Search className="w-8 h-8" />}
                title="No results found"
                description="Try adjusting your search query or removing filters."
              />
            )}
            {search.data.results.length > 0 && (
              <div className="mt-5 flex items-center justify-between gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-800/30">
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  {search.data.has_more
                    ? "More results are available."
                    : "You have reached the end of the results."}
                </p>
                {renderPager()}
              </div>
            )}
          </>
        ) : (
          <EmptyState
            icon={<Search className="w-10 h-10" />}
            title="Search your knowledge base"
            description="Enter a query to search across documents, wikis, issues, and more."
          />
        )}
      </div>
    </div>
  );
}
