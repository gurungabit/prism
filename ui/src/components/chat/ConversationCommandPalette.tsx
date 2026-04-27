import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { MessageCircle, Plus, Search, X } from "lucide-react";

import type { Conversation } from "../../stores/chat";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversations: Conversation[];
  onNew: () => void;
}

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

  const reactId = useId();
  const listboxId = `palette-listbox-${reactId}`;
  const newRowId = `palette-option-${reactId}-new`;
  const conversationOptionId = (id: string) => `palette-option-${reactId}-${id}`;

  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlight(0);
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  const ranked = useMemo(() => {
    const sorted = [...conversations].sort(
      (a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0),
    );
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((c) => {
      if (c.title?.toLowerCase().includes(q)) return true;
      if (c.lastMessage?.toLowerCase().includes(q)) return true;
      const lastMsg = c.messages[c.messages.length - 1];
      if (lastMsg?.content?.toLowerCase().includes(q)) return true;
      return false;
    });
  }, [conversations, query]);

  useEffect(() => {
    if (highlight > ranked.length) {
      setHighlight(ranked.length);
    }
  }, [ranked.length, highlight]);

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

  function commitConversation(conv: Conversation) {
    onOpenChange(false);
    navigate({ to: "/chat/$conversationId", params: { conversationId: conv.id } });
  }

  function commitNew() {
    onOpenChange(false);
    onNew();
    navigate({ to: "/chat" });
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

  const totalCommands = 1 + ranked.length;

  const flat: Array<
    | { kind: "header"; label: string }
    | { kind: "row"; conv: Conversation; commandIndex: number }
  > = [];
  let lastBucket: string | null = null;
  ranked.forEach((c, i) => {
    const b = bucket(c);
    if (b !== lastBucket) {
      flat.push({ kind: "header", label: b });
      lastBucket = b;
    }
    flat.push({ kind: "row", conv: c, commandIndex: i + 1 });
  });

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, totalCommands - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlight === 0) {
        commitNew();
      } else {
        const target = ranked[highlight - 1];
        if (target) commitConversation(target);
      }
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
            role="combobox"
            aria-expanded={true}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={(() => {
              if (highlight === 0) return newRowId;
              const target = ranked[highlight - 1];
              return target ? conversationOptionId(target.id) : undefined;
            })()}
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

        <div
          id={listboxId}
          role="listbox"
          aria-label="Commands and conversations"
          className="max-h-[60vh] overflow-y-auto"
        >
          {/* New-chat affordance always at the top -- always selectable
              as command index 0 so Cmd+K can act as a "go" launcher
              even before any conversations exist. */}
          <button
            type="button"
            id={newRowId}
            role="option"
            aria-selected={highlight === 0}
            // ``onPointerMove`` instead of ``onMouseEnter`` because
            // mouseenter fires when an element appears under a
            // stationary cursor (e.g. on palette open). That bumped
            // highlight off the keyboard-default of 0 if the cursor
            // happened to be over a conversation row when ⌘K was
            // pressed -- pointermove only fires on real movement, so
            // the keyboard-default sticks.
            onPointerMove={() => setHighlight(0)}
            onClick={commitNew}
            className={`
              w-full flex items-center gap-3 px-4 py-2.5 text-left
              text-[13px] text-zinc-700 dark:text-zinc-300
              border-b border-zinc-100 dark:border-zinc-700/40
              transition-colors duration-100
              ${
                highlight === 0
                  ? "bg-zinc-100 dark:bg-zinc-800/60"
                  : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
              }
            `}
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
              const { conv, commandIndex } = row;
              const isHighlighted = commandIndex === highlight;
              const lastMsg = conv.messages[conv.messages.length - 1];
              // Prefer in-session ``messages[last]`` over the
              // backend-snapshot ``lastMessage`` so a new turn the
              // user just sent isn't shadowed by stale list data.
              const preview =
                lastMsg?.content.slice(0, 80) ||
                conv.lastMessage ||
                "(empty conversation)";
              return (
                <button
                  key={conv.id}
                  id={conversationOptionId(conv.id)}
                  type="button"
                  role="option"
                  aria-selected={isHighlighted}
                  // See the New row -- pointermove not mouseenter so
                  // a static cursor over a fresh row doesn't bump
                  // the keyboard highlight off 0.
                  onPointerMove={() => setHighlight(commandIndex)}
                  onClick={() => commitConversation(conv)}
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
