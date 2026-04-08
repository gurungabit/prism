import { useMutation } from "@tanstack/react-query";
import { searchDocuments, type SearchParams } from "../lib/api";
import { SearchResponseSchema } from "../lib/schemas";

export function useSearchMutation() {
  return useMutation({
    mutationFn: async (params: SearchParams) => {
      const raw = await searchDocuments(params);
      return SearchResponseSchema.parse(raw);
    },
  });
}
