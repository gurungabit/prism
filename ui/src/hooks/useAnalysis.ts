import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  startAnalysis,
  getReport,
  getTrace,
  getHistory,
  deleteAnalysis,
  type AnalysisInput,
} from "../lib/api";
import { PRISMReportSchema } from "../lib/schemas";

export function useStartAnalysis() {
  return useMutation({
    mutationFn: (input: AnalysisInput) => startAnalysis(input),
  });
}

export function useReport(analysisId: string | null) {
  return useQuery({
    queryKey: ["report", analysisId],
    queryFn: async () => {
      if (!analysisId) throw new Error("No analysis ID");
      const raw = await getReport(analysisId);
      return PRISMReportSchema.parse(raw);
    },
    enabled: !!analysisId,
    staleTime: Infinity,
    retry: (count, error) => {
      if (error instanceof Error && error.message.includes("202")) return count < 30;
      return false;
    },
    retryDelay: 3000,
  });
}

export function useTrace(analysisId: string | null) {
  return useQuery({
    queryKey: ["trace", analysisId],
    queryFn: () => getTrace(analysisId!),
    enabled: !!analysisId,
    staleTime: Infinity,
  });
}

export function useHistory(limit = 20, offset = 0) {
  return useQuery({
    queryKey: ["history", limit, offset],
    queryFn: () => getHistory(limit, offset),
    staleTime: 10_000,
  });
}

export function useDeleteAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (analysisId: string) => deleteAnalysis(analysisId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });
}
