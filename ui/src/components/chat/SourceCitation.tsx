import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FileText } from "lucide-react";
import { getChatSourcePreview } from "../../lib/api";
import type { ChatCitation } from "../../stores/chat";
import { Badge } from "../shared/Badge";
import { Modal } from "../shared/Modal";

interface SourceCitationProps {
  label: string;
  citations: ChatCitation[];
  emptyMessage?: string;
}

function scoreLabel(score?: number) {
  if (typeof score !== "number" || Number.isNaN(score)) return null;
  const normalized = score > 1 ? score / 100 : score;
  return `${Math.round(normalized * 100)}%`;
}

function citationKey(citation: ChatCitation) {
  return `${citation.index}:${citation.platform}:${citation.source_path}`;
}

export function SourceCitation({
  label,
  citations,
  emptyMessage = "Source details are not available for this message yet. Ask the question again to regenerate the answer with source chunks attached.",
}: SourceCitationProps) {
  const [open, setOpen] = useState(false);
  const [loadedContent, setLoadedContent] = useState<Record<string, string>>({});
  const [loadingKeys, setLoadingKeys] = useState<Record<string, boolean>>({});
  const orderedCitations = useMemo(
    () => [...citations].sort((a, b) => a.index - b.index),
    [citations],
  );

  useEffect(() => {
    if (!open) return;

    const missing = orderedCitations.filter(
      (citation) => !citation.content?.trim() && !citation.excerpt?.trim(),
    );
    if (missing.length === 0) return;

    let cancelled = false;

    setLoadingKeys((current) => {
      const next = { ...current };
      for (const citation of missing) {
        next[citationKey(citation)] = true;
      }
      return next;
    });

    void Promise.all(
      missing.map(async (citation) => {
        try {
          const preview = await getChatSourcePreview(citation.source_path, citation.platform);
          return { key: citationKey(citation), content: preview.content || "" };
        } catch (err) {
          console.warn(
            `[SourceCitation] Failed to fetch preview for "${citation.source_path}":`,
            err,
          );
          return { key: citationKey(citation), content: "" };
        }
      }),
    ).then((results) => {
      if (cancelled) return;

      setLoadedContent((current) => {
        const next = { ...current };
        for (const result of results) {
          if (result.content) {
            next[result.key] = result.content;
          }
        }
        return next;
      });

      setLoadingKeys((current) => {
        const next = { ...current };
        for (const citation of missing) {
          delete next[citationKey(citation)];
        }
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [open, orderedCitations]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center rounded-md border border-[var(--color-accent-subtle)] bg-[var(--color-accent-muted)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-subtle)] dark:border-[var(--color-accent-dark-subtle)] dark:bg-[var(--color-accent-dark-muted)] dark:text-[var(--color-accent-dark)] dark:hover:bg-[var(--color-accent-dark-subtle)]"
      >
        {label}
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={label}
        width="max-w-3xl"
      >
        <div className="space-y-4">
          {orderedCitations.length === 0 ? (
            <div className="rounded-xl border border-zinc-200/70 bg-zinc-50/70 px-4 py-4 text-[13px] leading-relaxed text-zinc-600 dark:border-zinc-700/40 dark:bg-zinc-800/30 dark:text-zinc-300">
              {emptyMessage}
            </div>
          ) : (
            <>
          <div className="rounded-xl border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 text-[12px] text-zinc-600 dark:border-zinc-700/40 dark:bg-zinc-800/30 dark:text-zinc-300">
            {orderedCitations.length === 1
              ? "This answer references one matching chunk."
              : `This answer references ${orderedCitations.length} matching chunks.`}
          </div>

          <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
            {orderedCitations.map((citation) => {
              const title = citation.title?.trim() || citation.source_path;
              const hasSourceUrl = Boolean(citation.source_url);
              const score = scoreLabel(citation.score);
              const key = citationKey(citation);
              const chunkText = citation.content?.trim()
                || loadedContent[key]?.trim()
                || citation.excerpt?.trim()
                || "";
              const isLoading = Boolean(loadingKeys[key]);

              return (
                <div
                  key={`${citation.index}-${citation.source_path}`}
                  className="rounded-xl border border-zinc-200/70 bg-white px-4 py-4 shadow-sm dark:border-zinc-700/40 dark:bg-[#1b1b1d]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge variant="accent" size="sm">
                          {`Source ${citation.index}`}
                        </Badge>
                        {citation.platform && (
                          <Badge variant="neutral" size="sm">
                            {citation.platform}
                          </Badge>
                        )}
                        {citation.section_heading && (
                          <Badge variant="info" size="sm">
                            {citation.section_heading}
                          </Badge>
                        )}
                      </div>

                      <div className="flex items-start gap-2">
                        <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-400 dark:text-zinc-500" />
                        <div className="min-w-0">
                          <div className="text-[14px] font-medium leading-snug text-zinc-900 dark:text-zinc-100">
                            {title}
                          </div>
                          <div
                            className="mt-1 break-all text-[11px] font-mono leading-relaxed text-zinc-500 dark:text-zinc-400"
                            title={citation.source_path}
                          >
                            {citation.source_path}
                          </div>
                        </div>
                      </div>
                    </div>

                    {score && (
                      <div className="flex-shrink-0 text-[11px] font-mono text-zinc-400 dark:text-zinc-500">
                        {score}
                      </div>
                    )}
                  </div>

                  <div className="mt-3 rounded-lg border border-zinc-100 bg-zinc-50/90 px-3 py-3 dark:border-zinc-700/40 dark:bg-zinc-800/40">
                    <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                      Matching Chunk
                    </div>
                    <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-zinc-700 dark:text-zinc-300">
                      {chunkText || (isLoading
                        ? "Loading chunk preview..."
                        : "No chunk preview available for this source.")}
                    </p>
                  </div>

                  <div className="mt-3 flex items-center justify-between gap-3">
                    <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
                      {hasSourceUrl
                        ? "Open the original source document."
                        : "A direct source link is not available for this dataset yet."}
                    </div>
                    {hasSourceUrl && (
                      <a
                        href={citation.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200/80 bg-zinc-50 px-2.5 py-1.5 text-[12px] font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700/40 dark:bg-zinc-800/40 dark:text-zinc-200 dark:hover:bg-zinc-700/40"
                      >
                        Open Source
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
            </>
          )}
        </div>
      </Modal>
    </>
  );
}
