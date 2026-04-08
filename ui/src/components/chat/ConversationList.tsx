import { useState } from "react";
import { Link } from "@tanstack/react-router";
import type { Conversation } from "../../stores/chat";
import { MessageCircle, SquarePen, Trash2 } from "lucide-react";

interface ConversationListProps {
  conversations: Conversation[];
  activeId: string | null;
  onNew: () => void;
  onDelete?: (id: string) => void;
}

function ConfirmDeleteModal({
  open,
  onClose,
  onConfirm,
  title,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
}) {
  if (!open) return null;

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
    >
      <div className="w-full max-w-sm mx-4 rounded-xl border border-zinc-200 dark:border-zinc-700/40 bg-white dark:bg-[#1e1e20] shadow-xl">
        <div className="px-5 pt-5 pb-2">
          <p className="text-[14px] font-medium text-zinc-900 dark:text-zinc-100">
            Delete conversation?
          </p>
          <p className="text-[12px] text-zinc-500 dark:text-zinc-400 mt-1.5 leading-relaxed">
            <span className="font-medium text-zinc-600 dark:text-zinc-300">{title}</span>
            {" "}will be permanently deleted.
          </p>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-4">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-[12px] font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-700/40 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 rounded-lg text-[12px] font-medium bg-red-500/90 text-white hover:bg-red-600 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

export function ConversationList({
  conversations,
  activeId,
  onNew,
  onDelete,
}: ConversationListProps) {
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);

  function handleConfirmDelete() {
    if (deleteTarget && onDelete) {
      onDelete(deleteTarget.id);
    }
    setDeleteTarget(null);
  }

  return (
    <>
      <div className="flex flex-col h-full border-r border-zinc-200/70 dark:border-zinc-700/40 bg-white dark:bg-[#1a1a1c] w-56">
        <div className="flex items-center justify-between px-3 py-3 border-b border-zinc-100 dark:border-zinc-700/40">
          <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            Conversations
          </span>
          <button
            onClick={onNew}
            aria-label="New conversation"
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700/30 transition-colors duration-150"
          >
            <SquarePen className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-1">
          {conversations.length === 0 ? (
            <div className="flex flex-col items-center px-4 py-12 text-center">
              <MessageCircle className="w-6 h-6 text-zinc-200 dark:text-zinc-700 mb-3" />
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mb-3">
                No conversations yet
              </p>
              <button
                onClick={onNew}
                className="text-[11px] font-medium text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:opacity-80 transition-opacity"
              >
                Start your first chat
              </button>
            </div>
          ) : (
            conversations.map((conv) => {
              const isActive = activeId === conv.id;
              const lastMsg = conv.messages[conv.messages.length - 1];
              const preview = lastMsg?.content.slice(0, 50) || "Empty conversation";

              return (
                <div
                  key={conv.id}
                  className="group relative mx-1"
                  style={{ width: "calc(100% - 8px)" }}
                >
                  <Link
                    to="/chat/$conversationId"
                    params={{ conversationId: conv.id }}
                    className={`
                      flex flex-col w-full px-3 py-2 rounded-lg text-left
                      transition-all duration-150
                      ${
                        isActive
                          ? "bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)]"
                          : "hover:bg-zinc-50 dark:hover:bg-zinc-700/30"
                      }
                    `}
                  >
                    <span
                      className={`text-[12px] truncate pr-5 ${
                        isActive
                          ? "text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] font-medium"
                          : "text-zinc-600 dark:text-zinc-400"
                      }`}
                    >
                      {conv.title}
                    </span>
                    <span className="text-[10px] text-zinc-400 dark:text-zinc-500 truncate mt-0.5 pr-5">
                      {preview}
                    </span>
                  </Link>

                  {onDelete && (
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setDeleteTarget({ id: conv.id, title: conv.title });
                      }}
                      aria-label="Delete conversation"
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-zinc-100 dark:hover:bg-zinc-700/40 transition-all duration-150"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      <ConfirmDeleteModal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
        title={deleteTarget?.title ?? ""}
      />
    </>
  );
}
