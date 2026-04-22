// Re-exports kept for backwards compatibility with the old /sources page.
// The declared-source hooks live in ./useCatalog.
export {
  useDeclaredSources as useSources,
  useDeclaredSource,
  useCreateSource,
  useUpdateSource,
  useDeleteSource,
  useTriggerIngest,
  useSourceStatus,
  useValidateSource,
} from "./useCatalog";
