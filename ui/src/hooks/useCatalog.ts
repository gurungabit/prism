import { useEffect, useRef } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  addExternalServiceDependency,
  addServiceDependency,
  createOrg,
  createService,
  createSource,
  createTeam,
  deleteExternalServiceDependency,
  deleteOrg,
  deleteService,
  deleteServiceDependency,
  deleteSource,
  deleteTeam,
  getDeclaredSource,
  getOrg,
  getServiceById,
  getSourceStatus,
  getTeam,
  listDeclaredSources,
  listOrgs,
  listServiceDependencies,
  listServicesForTeam,
  listSourceDocuments,
  listTeamsForOrg,
  triggerSourceIngest,
  updateOrg,
  updateService,
  updateSource,
  updateTeam,
  validateSource,
  type CreateSourceBody,
  type ValidateSourceBody,
} from "../lib/api";

// Org/team/service mutations affect the same derived topology caches.
function _invalidateCatalogTopology(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["orgs"] });
  qc.invalidateQueries({ queryKey: ["teams-for-org"] });
  qc.invalidateQueries({ queryKey: ["teams"] });
  qc.invalidateQueries({ queryKey: ["services-for-team"] });
  qc.invalidateQueries({ queryKey: ["services-for-org"] });
  qc.invalidateQueries({ queryKey: ["organization-graph"] });
}

// Cascade deletes in Postgres take every descendant source with them.
// We don't know which source ids got dropped, so refetch the list query
// and remove every per-source detail/document cache wholesale -- each
// is cheap to refetch lazily on the next view.
function _dropSourceCachesAfterCascade(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["declared-sources"] });
  qc.removeQueries({ queryKey: ["declared-source"] });
  qc.removeQueries({ queryKey: ["declared-source-status"] });
  qc.removeQueries({ queryKey: ["source-documents"] });
}

// ---------- orgs ----------

export function useOrgs() {
  return useQuery({
    queryKey: ["orgs"],
    queryFn: listOrgs,
    staleTime: 60_000,
  });
}

export function useOrg(orgId: string | undefined) {
  return useQuery({
    queryKey: ["org", orgId],
    queryFn: () => getOrg(orgId!),
    enabled: !!orgId,
    staleTime: 60_000,
  });
}

export function useCreateOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createOrg(name),
    onSuccess: () => _invalidateCatalogTopology(qc),
  });
}

export function useUpdateOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orgId, name }: { orgId: string; name: string }) => updateOrg(orgId, name),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["org", vars.orgId] });
      _invalidateCatalogTopology(qc);
    },
  });
}

export function useDeleteOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orgId: string) => deleteOrg(orgId),
    onSuccess: (_data, orgId) => {
      _invalidateCatalogTopology(qc);
      _dropSourceCachesAfterCascade(qc);
      // Cascade also pulls every descendant team / service with the
      // org. We don't have their ids here, so drop the per-entity
      // caches wholesale.
      qc.removeQueries({ queryKey: ["org", orgId] });
      qc.removeQueries({ queryKey: ["teams-for-org", orgId] });
      qc.removeQueries({ queryKey: ["team"] });
      qc.removeQueries({ queryKey: ["service-by-id"] });
      qc.removeQueries({ queryKey: ["service-dependencies"] });
    },
  });
}

// ---------- teams ----------

export function useTeamsForOrg(orgId: string | undefined) {
  return useQuery({
    queryKey: ["teams-for-org", orgId],
    queryFn: () => listTeamsForOrg(orgId!),
    enabled: !!orgId,
    staleTime: 30_000,
  });
}

export function useTeamById(teamId: string | undefined) {
  return useQuery({
    queryKey: ["team", teamId],
    queryFn: () => getTeam(teamId!),
    enabled: !!teamId,
    staleTime: 30_000,
  });
}

export function useCreateTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      orgId,
      body,
    }: {
      orgId: string;
      body: { name: string; description?: string };
    }) => createTeam(orgId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["teams-for-org", vars.orgId] });
      _invalidateCatalogTopology(qc);
    },
  });
}

export function useUpdateTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      teamId,
      body,
    }: {
      teamId: string;
      body: { name?: string; description?: string };
    }) => updateTeam(teamId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["team", vars.teamId] });
      _invalidateCatalogTopology(qc);
    },
  });
}

export function useDeleteTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string) => deleteTeam(teamId),
    onSuccess: (_data, teamId) => {
      // A team delete cascades services + sources in Postgres. The
      // topology helper handles the derived list queries; the rest
      // wipes per-entity detail caches that would otherwise display
      // rows the backend has already deleted.
      _invalidateCatalogTopology(qc);
      _dropSourceCachesAfterCascade(qc);
      qc.removeQueries({ queryKey: ["team", teamId] });
      qc.removeQueries({ queryKey: ["services-for-team", teamId] });
      qc.removeQueries({ queryKey: ["service-by-id"] });
      qc.removeQueries({ queryKey: ["service-dependencies"] });
    },
  });
}

// ---------- services ----------

export function useServicesForTeam(teamId: string | undefined) {
  return useQuery({
    queryKey: ["services-for-team", teamId],
    queryFn: () => listServicesForTeam(teamId!),
    enabled: !!teamId,
    staleTime: 30_000,
  });
}

export function useServiceById(serviceId: string | undefined) {
  return useQuery({
    queryKey: ["service-by-id", serviceId],
    queryFn: () => getServiceById(serviceId!),
    enabled: !!serviceId,
    staleTime: 30_000,
  });
}

export function useCreateService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      teamId,
      body,
    }: {
      teamId: string;
      body: { name: string; repo_url?: string; description?: string };
    }) => createService(teamId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["services-for-team", vars.teamId] });
      _invalidateCatalogTopology(qc);
    },
  });
}

export function useUpdateService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      serviceId,
      body,
    }: {
      serviceId: string;
      body: { name?: string; repo_url?: string; description?: string };
    }) => updateService(serviceId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["service-by-id", vars.serviceId] });
      _invalidateCatalogTopology(qc);
    },
  });
}

export function useDeleteService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (serviceId: string) => deleteService(serviceId),
    onSuccess: (_data, serviceId) => {
      _invalidateCatalogTopology(qc);
      _dropSourceCachesAfterCascade(qc);
      qc.removeQueries({ queryKey: ["service-by-id", serviceId] });
      qc.removeQueries({ queryKey: ["service-dependencies", serviceId] });
    },
  });
}

// ---------- service dependencies ----------

export function useServiceDependencies(serviceId: string | undefined) {
  return useQuery({
    queryKey: ["service-dependencies", serviceId],
    queryFn: () => listServiceDependencies(serviceId!),
    enabled: !!serviceId,
    staleTime: 15_000,
  });
}

export function useAddServiceDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ serviceId, toServiceId }: { serviceId: string; toServiceId: string }) =>
      addServiceDependency(serviceId, toServiceId),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["service-dependencies", vars.serviceId] });
      qc.invalidateQueries({ queryKey: ["organization-graph"] });
    },
  });
}

export function useDeleteServiceDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ serviceId, toServiceId }: { serviceId: string; toServiceId: string }) =>
      deleteServiceDependency(serviceId, toServiceId),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["service-dependencies", vars.serviceId] });
      qc.invalidateQueries({ queryKey: ["organization-graph"] });
    },
  });
}

export function useAddExternalServiceDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      serviceId,
      name,
      description,
    }: {
      serviceId: string;
      name: string;
      description: string;
    }) => addExternalServiceDependency(serviceId, name, description),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["service-dependencies", vars.serviceId] });
      // External edges don't render on the org graph (no node to draw to)
      // so we skip invalidating that query.
    },
  });
}

export function useDeleteExternalServiceDependency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ serviceId, name }: { serviceId: string; name: string }) =>
      deleteExternalServiceDependency(serviceId, name),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["service-dependencies", vars.serviceId] });
    },
  });
}

// ---------- sources ----------

export function useDeclaredSources(filter?: {
  orgId?: string;
  teamId?: string;
  serviceId?: string;
}) {
  return useQuery({
    queryKey: ["declared-sources", filter],
    queryFn: () => listDeclaredSources(filter),
    staleTime: 15_000,
  });
}

export function useDeclaredSource(sourceId: string | undefined) {
  return useQuery({
    queryKey: ["declared-source", sourceId],
    queryFn: () => getDeclaredSource(sourceId!),
    enabled: !!sourceId,
    staleTime: 15_000,
  });
}

const SOURCE_DOCUMENTS_PAGE_SIZE = 50;

export function useSourceDocumentsInfinite(sourceId: string | undefined) {
  return useInfiniteQuery({
    queryKey: ["source-documents", sourceId],
    enabled: !!sourceId,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      listSourceDocuments(sourceId!, {
        offset: pageParam,
        limit: SOURCE_DOCUMENTS_PAGE_SIZE,
      }),
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.offset + lastPage.limit : undefined,
    staleTime: 15_000,
  });
}

export function useSourceStatus(sourceId: string | undefined, enabled = true) {
  const qc = useQueryClient();
  const prevStatusRef = useRef<string | null>(null);
  const query = useQuery({
    queryKey: ["declared-source-status", sourceId],
    queryFn: () => getSourceStatus(sourceId!),
    enabled: !!sourceId && enabled,
    refetchInterval: (q) => {
      // Poll every 3s while the source is actively syncing so the UI moves
      // off "Syncing..." without a manual refresh. Stop once it settles.
      const status = q.state.data?.status;
      return status === "syncing" || status === "pending" ? 3_000 : false;
    },
  });

  useEffect(() => {
    const current = query.data?.status;
    if (!current || !sourceId) return;
    const prev = prevStatusRef.current;
    if (
      (prev === "syncing" || prev === "pending") &&
      current !== "syncing" &&
      current !== "pending"
    ) {
      qc.invalidateQueries({ queryKey: ["declared-source", sourceId] });
      qc.invalidateQueries({ queryKey: ["declared-sources"] });
      qc.invalidateQueries({ queryKey: ["source-documents", sourceId] });
    }
    prevStatusRef.current = current;
  }, [query.data?.status, sourceId, qc]);

  return query;
}

export function useCreateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateSourceBody) => createSource(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["declared-sources"] }),
  });
}

export function useUpdateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceId,
      body,
    }: {
      sourceId: string;
      body: { name?: string; config?: Record<string, unknown>; token?: string };
    }) => updateSource(sourceId, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["declared-source", vars.sourceId] });
      qc.invalidateQueries({ queryKey: ["declared-sources"] });
      qc.invalidateQueries({ queryKey: ["source-documents", vars.sourceId] });
    },
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => deleteSource(sourceId),
    onSuccess: (_data, sourceId) => {
      qc.invalidateQueries({ queryKey: ["declared-sources"] });
      qc.removeQueries({ queryKey: ["source-documents", sourceId] });
      qc.removeQueries({ queryKey: ["declared-source", sourceId] });
    },
  });
}

export function useTriggerIngest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceId, force = false }: { sourceId: string; force?: boolean }) =>
      triggerSourceIngest(sourceId, force),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["declared-source", vars.sourceId] });
      qc.invalidateQueries({ queryKey: ["declared-source-status", vars.sourceId] });
      qc.invalidateQueries({ queryKey: ["declared-sources"] });
      // Force re-index wipes every chunk + registry row before
      // re-ingesting; even a normal sync can churn the doc set.
      // Either way the cached pages are stale -- invalidate so the
      // detail page refetches once the sync settles.
      qc.invalidateQueries({ queryKey: ["source-documents", vars.sourceId] });
    },
  });
}

export function useValidateSource() {
  return useMutation({
    mutationFn: (body: ValidateSourceBody) => validateSource(body),
  });
}
