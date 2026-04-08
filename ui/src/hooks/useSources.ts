import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getSourcesList, triggerIngest, triggerPlatformIngest, triggerFullIngest } from "../lib/api";

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => getSourcesList(),
    staleTime: 30_000,
  });
}

export function useIngest() {
  const qc = useQueryClient();

  const ingest = useMutation({
    mutationFn: () => triggerIngest(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  const platformIngest = useMutation({
    mutationFn: (platform: string) => triggerPlatformIngest(platform),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  const fullIngest = useMutation({
    mutationFn: () => triggerFullIngest(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  return { ingest, platformIngest, fullIngest };
}
