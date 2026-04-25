import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { MessageCircle, Plus, Search, X } from "lucide-react";

import type { Conversation } from "../../stores/chat";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversations: Conversation[];
  onNew: () => void;
}

// Cmd+K / Ctrl+K command palette for jumping to (and searching) chat
// conversations. Modeled on the "Search chats and projects" palette
// in the user-supplied screenshot: a floating modal with a search
// input and a keyboard-navigable list of matches grouped by recency.
//
// Matching is case-insensitive substring on title + last-message
// preview. ↑/↓ moves the highlight, Enter opens, Esc closes.
// Clicking outside also closes.
export function ConversationCommandPalette({
  open,
  onOpenChange,
  conversations,
  onNew,
}: Props) {
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset query + focus the input every time the palette opens. Without
  // the reset, a previous typed query would still be in the box on
  // re-open, which feels broken when the user is jumping in fresh.
  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlight(0);
      // Defer focus to after the modal mounts so the focus call hits
      // the rendered input.
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Sort by recency, then bucket. A chat with no messages keeps its
  // ``updatedAt`` (set when created) so brand-new empty chats still
  // surface near the top.
  const ranked = useMemo(() => {
    const sorted = [...conversations].sort(
      (a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0),
    );
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((c) => {
      if (c.title?.toLowerCase().includes(q)) return true;
      const lastMsg = c.messages[c.messages.length - 1];
      if (lastMsg?.content?.toLowerCase().includes(q)) return true;
      return false;
    });
  }, [conversations, query]);

  // Keep the highlighted index inside the visible range when the
  // filter shrinks. Without this, a previously-valid index can point
  // past the end of ``ranked``.
  useEffect(() => {
    if (highlight >= ranked.length) {
      setHighlight(Math.max(0, ranked.length - 1));
    }
  }, [ranked.length, highlight]);

  // Close on outside click. The overlay div catches the click and
  // forwards close only when the click target is the overlay itself
  // (i.e. not inside the modal card).
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        onOpenChange(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onOpenChange]);

  if (!open) return null;

  function commit(conv: Conversation) {
    onOpenChange(false);
    navigate({ to: "/chat/$conversationId", params: { conversationId: conv.id } });
  }

  function bucket(conv: Conversation): string {
    const now = Date.now();
    const ts = conv.updatedAt ?? 0;
    const dayMs = 86_400_000;
    if (now - ts < dayMs) return "Today";
    if (now - ts < 2 * dayMs) return "Yesterday";
    if (now - ts < 7 * dayMs) return "Past week";
    return "Older";
  }

  // Build the flat list with bucket headers interleaved. We track the
  // selectable index in parallel so ``aria-activedescendant`` and the
  // visual highlight stay in lockstep with the keyboard nav.
  const flat: Array<
    | { kind: "header"; label: string }
    | { kind: "row"; conv: Conversation; index: number }
  > = [];
  let lastBucket: string | null = null;
  ranked.forEach((c, i) => {
    const b = bucket(c);
    if (b !== lastBucket) {
      flat.push({ kind: "header", label: b });
      lastBucket = b;
    }
    flat.push({ kind: "row", conv: c, index: i });
  });

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, ranked.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = ranked[highlight];
      if (target) commit(target);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onOpenChange(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Search conversations"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 backdrop-blur-[2px] pt-[15vh] px-4"
    >
      <div
        ref={containerRef}
        className="
          w-full max-w-xl rounded-xl border border-zinc-200 dark:border-zinc-700/40
          bg-white dark:bg-[#1e1e20] shadow-2xl
          overflow-hidden
        "
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-100 dark:border-zinc-700/40">
          <Search className="w-4 h-4 text-zinc-400" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search conversations…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setHighlight(0);
            }}
            onKeyDown={onKeyDown}
            className="flex-1 bg-transparent outline-none text-[13px] text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-600"
          />
          <button
            type="button"
            aria-label="Close"
            onClick={() => onOpenChange(false)}
            className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {/* New-chat affordance always at the top so Cmd+K can act as
              a "go" launcher even before any conversations exist. */}
          <button
            type="button"
            onClick={() => {
              onOpenChange(false);
              onNew();
              navigate({ to: "/chat" });
            }}
            className="
              w-full flex items-center gap-3 px-4 py-2.5 text-left
              text-[13px] text-zinc-700 dark:text-zinc-300
              hover:bg-zinc-50 dark:hover:bg-zinc-800/50
              border-b border-zinc-100 dark:border-zinc-700/40
            "
          >
            <Plus className="w-4 h-4 text-zinc-400" aria-hidden="true" />
            <span>New conversation</span>
            <span className="ml-auto text-[10px] text-zinc-400 dark:text-zinc-500">
              ↵
            </span>
          </button>

          {ranked.length === 0 ? (
            <div className="px-4 py-10 flex flex-col items-center text-center">
              <MessageCircle className="w-5 h-5 text-zinc-300 dark:text-zinc-600 mb-2" />
              <p className="text-[12px] text-zinc-500 dark:text-zinc-400">
                {conversations.length === 0
                  ? "No conversations yet."
                  : "No conversations match that query."}
              </p>
            </div>
          ) : (
            flat.map((row) => {
              if (row.kind === "header") {
                return (
                  <div
                    key={`bucket-${row.label}`}
                    role="presentation"
                    className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500"
                  >
                    {row.label}
                  </div>
                );
              }
              const { conv, index } = row;
              const isHighlighted = index === highlight;
              const lastMsg = conv.messages[conv.messages.length - 1];
              const preview =
                lastMsg?.content.slice(0, 80) || "(empty conversation)";
              return (
                <button
                  key={conv.id}
                  type="button"
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => commit(conv)}
                  className={`
                    w-full text-left px-4 py-2.5
                    transition-colors duration-100
                    ${
                      isHighlighted
                        ? "bg-zinc-100 dark:bg-zinc-800/60"
                        : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
                    }
                  `}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[13px] text-zinc-900 dark:text-zinc-100 truncate font-medium">
                      {conv.title || "Untitled"}
                    </span>
                  </div>
                  <span className="block text-[11px] text-zinc-500 dark:text-zinc-500 truncate mt-0.5">
                    {preview}
                  </span>
                </button>
              );
            })
          )}
        </div>

        <div className="flex items-center justify-between px-4 py-2 border-t border-zinc-100 dark:border-zinc-700/40 text-[10px] text-zinc-400 dark:text-zinc-500">
          <span>Search across {conversations.length} conversation{conversations.length === 1 ? "" : "s"}</span>
          <span>↑↓ navigate · ↵ open · esc close</span>
        </div>
      </div>
    </div>
  );
}
