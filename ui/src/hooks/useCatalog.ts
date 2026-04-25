import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orgs"] }),
  });
}

export function useUpdateOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orgId, name }: { orgId: string; name: string }) => updateOrg(orgId, name),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["orgs"] });
      qc.invalidateQueries({ queryKey: ["org", vars.orgId] });
    },
  });
}

export function useDeleteOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orgId: string) => deleteOrg(orgId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orgs"] }),
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
      qc.invalidateQueries({ queryKey: ["teams"] });
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
      qc.invalidateQueries({ queryKey: ["teams-for-org"] });
      qc.invalidateQueries({ queryKey: ["teams"] });
    },
  });
}

export function useDeleteTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string) => deleteTeam(teamId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["teams-for-org"] });
      qc.invalidateQueries({ queryKey: ["teams"] });
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
      qc.invalidateQueries({ queryKey: ["teams"] });
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
      qc.invalidateQueries({ queryKey: ["services-for-team"] });
    },
  });
}

export function useDeleteService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (serviceId: string) => deleteService(serviceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["services-for-team"] });
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
    // Transition from active (syncing/pending) to settled (ready/error)
    // means ``document_count`` and ``documents`` are now stale on the
    // detail view. Invalidate so they refetch without a manual reload.
    if (
      (prev === "syncing" || prev === "pending") &&
      current !== "syncing" &&
      current !== "pending"
    ) {
      qc.invalidateQueries({ queryKey: ["declared-source", sourceId] });
      qc.invalidateQueries({ queryKey: ["declared-sources"] });
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
    },
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => deleteSource(sourceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["declared-sources"] }),
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
    },
  });
}

export function useValidateSource() {
  return useMutation({
    mutationFn: (body: ValidateSourceBody) => validateSource(body),
  });
}
