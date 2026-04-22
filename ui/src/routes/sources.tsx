import { Link } from "@tanstack/react-router";
import { Plus, Plug, Sparkles } from "lucide-react";

import { Button } from "../components/shared/Button";
import { EmptyState } from "../components/shared/EmptyState";
import { Skeleton } from "../components/shared/Skeleton";
import { DeclaredSourceRow } from "../components/sources/DeclaredSourceRow";
import { useDeclaredSources } from "../hooks/useCatalog";
import { useOrgs } from "../hooks/useCatalog";

/**
 * Lists every declared source across the org. Each row is a declared source,
 * not a connector "platform" -- so if the user attached the GitLab connector
 * three times under different teams/services, three rows show up.
 */
export function SourcesPage() {
  const sources = useDeclaredSources();
  const orgs = useOrgs();

  const sourceList = sources.data?.sources ?? [];
  const hasOrg = (orgs.data?.orgs ?? []).length > 0;

  return (
    <div className="max-w-[1000px] mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100">
            Sources
          </h1>
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500 mt-1">
            Declared data sources attached to your org, teams, or individual
            services.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/sources/new">
            <Button size="sm" icon={<Plus className="w-3.5 h-3.5" />}>
              Add source
            </Button>
          </Link>
        </div>
      </div>

      {sources.isLoading ? (
        <div className="space-y-0">
          <div className="py-3.5 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-2">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <div className="py-3.5 border-b border-zinc-200/60 dark:border-zinc-700/30 space-y-2">
            <Skeleton className="h-3.5 w-1/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ) : !hasOrg ? (
        <EmptyState
          icon={<Sparkles className="w-10 h-10" />}
          title="Set up your organization first"
          description="PRISM needs at least an org and a team before you can attach a source."
          action={
            <Link to="/">
              <Button size="sm">Create your org</Button>
            </Link>
          }
        />
      ) : sourceList.length > 0 ? (
        <div className="stagger-children">
          {sourceList.map((source) => (
            <DeclaredSourceRow key={source.id} source={source} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Plug className="w-10 h-10" />}
          title="No sources attached yet"
          description="Connect GitLab or another source to populate the knowledge base. Every document it fetches carries the scope you declared."
          action={
            <Link to="/sources/new">
              <Button size="sm" icon={<Plus className="w-3.5 h-3.5" />}>
                Add source
              </Button>
            </Link>
          }
        />
      )}
    </div>
  );
}
