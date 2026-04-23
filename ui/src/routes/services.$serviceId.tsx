import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, Plug, ExternalLink } from "lucide-react";

import { Button } from "../components/shared/Button";
import { Skeleton } from "../components/shared/Skeleton";
import { EmptyState } from "../components/shared/EmptyState";
import { Badge } from "../components/shared/Badge";
import { DeclaredSourceRow } from "../components/sources/DeclaredSourceRow";
import { useDeclaredSources, useServiceById } from "../hooks/useCatalog";

export function ServiceDetailPage() {
  const { serviceId } = useParams({ strict: false }) as { serviceId: string };
  const service = useServiceById(serviceId);
  const serviceSources = useDeclaredSources({ serviceId });

  const sourceList = serviceSources.data?.sources ?? [];

  if (service.isLoading) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8 space-y-6">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!service.data) {
    return (
      <div className="max-w-[960px] mx-auto px-6 py-8">
        <EmptyState
          title="Service not found"
          action={
            <Link to="/">
              <Button>Back to dashboard</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </button>
          <h1 className="text-lg tracking-tight text-zinc-900 dark:text-zinc-100 mt-1">
            {service.data.name}
          </h1>
          {service.data.description && (
            <p className="text-[12px] text-zinc-500 dark:text-zinc-400 mt-1 max-w-xl">
              {service.data.description}
            </p>
          )}
          {service.data.repo_url && (
            <a
              href={service.data.repo_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] mt-2 hover:underline"
            >
              {service.data.repo_url}
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
        <Link to="/sources/new" search={{ scope: "service", scopeId: serviceId }}>
          <Button variant="secondary" size="sm" icon={<Plug className="w-3.5 h-3.5" />}>
            Add service-level source
          </Button>
        </Link>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Service-level sources
          </h2>
          <Badge variant="info" size="sm">
            narrowest scope
          </Badge>
        </div>

        {serviceSources.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : sourceList.length > 0 ? (
          <div>
            {sourceList.map((src) => (
              <DeclaredSourceRow key={src.id} source={src} />
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            No service-level sources yet. These attach to this single service
            and are typically its own GitLab project / repo docs.
          </p>
        )}
      </section>
    </div>
  );
}
