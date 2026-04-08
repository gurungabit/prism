import { useQuery } from "@tanstack/react-query";
import {
  healthCheck,
  getTeams,
  getTeamProfile,
  getService,
  getDependencies,
  getConflicts,
} from "../lib/api";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: healthCheck,
    staleTime: 30_000,
    retry: false,
  });
}

export function useTeams() {
  return useQuery({
    queryKey: ["teams"],
    queryFn: getTeams,
    staleTime: 60_000,
    retry: false,
  });
}

export function useTeamProfile(teamName: string | null) {
  return useQuery({
    queryKey: ["team-profile", teamName],
    queryFn: () => getTeamProfile(teamName!),
    enabled: !!teamName,
    staleTime: 60_000,
  });
}

export function useService(serviceName: string | null) {
  return useQuery({
    queryKey: ["service", serviceName],
    queryFn: () => getService(serviceName!),
    enabled: !!serviceName,
    staleTime: 60_000,
  });
}

export function useDependencies(serviceName: string | null, depth = 2) {
  return useQuery({
    queryKey: ["dependencies", serviceName, depth],
    queryFn: () => getDependencies(serviceName!, depth),
    enabled: !!serviceName,
    staleTime: 60_000,
  });
}

export function useConflicts() {
  return useQuery({
    queryKey: ["conflicts"],
    queryFn: getConflicts,
    staleTime: 60_000,
    retry: false,
  });
}
