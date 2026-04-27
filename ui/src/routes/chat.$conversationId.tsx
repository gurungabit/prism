import { useRef, useEffect, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { ArrowDown } from "lucide-react";
import { useChat, useConversation, useConversations, useDeleteConversation } from "../hooks/useChat";
import { useChatStore } from "../stores/chat";
import { ConversationList } from "../components/chat/ConversationList";
import { ConversationCommandPalette } from "../components/chat/ConversationCommandPalette";
import { useCommandPalette } from "../hooks/useCommandPalette";
import { ChatMessage } from "../components/chat/ChatMessage";
import { ChatInput } from "../components/chat/ChatInput";
import { ScopeSelector, type ScopeValue } from "../components/catalog/ScopeSelector";

// Pixels from the bottom we still consider "at the bottom". Anything
// greater means the user has scrolled up and the auto-scroll should
// stop fighting them; the floating "scroll to bottom" button takes
// over instead.
const NEAR_BOTTOM_THRESHOLD = 80;

export function ChatConversationPage() {
  const { conversationId } = useParams({ from: "/chat/$conversationId" });
  const navigate = useNavigate();
  const chat = useChat();
  const deleteMutation = useDeleteConversation();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Conversation-local retrieval scope. Lives only on the page (not in
  // the chat store) -- the user can flip scope mid-thread and the next
  // ``sendMessage`` picks it up. Scope is forwarded to the chat API so
  // OpenSearch only grounds on chunks inside the selected catalog scope.
  const [scope, setScope] = useState<ScopeValue>({
    org_id: undefined,
    team_ids: [],
    service_ids: [],
  });
  const [scopeOpen, setScopeOpen] = useState(false);

  const conversationsQuery = useConversations();

  useEffect(() => {
    if (conversationsQuery.data?.conversations) {
      chat.loadFromBackend(conversationsQuery.data.conversations);
    }
  }, [conversationsQuery.data]);

  const localConversation = chat.conversations.find((c) => c.id === conversationId);
  const hasLocalMessages = localConversation && localConversation.messages.length > 0;
  const backendQuery = useConversation(hasLocalMessages ? null : conversationId);

  const setActiveConversation = useChatStore((s) => s.setActiveConversation);
  const palette = useCommandPalette();

  useEffect(() => {
    if (backendQuery.data) {
      const msgs = backendQuery.data.messages.map((m, i) => ({
        id: `${conversationId}-${i}`,
        role: m.role as "user" | "assistant",
        content: m.content,
        citations: m.citations,
        timestamp: Date.now(),
      }));
      useChatStore.setState((s) => ({
        conversations: s.conversations.some((c) => c.id === conversationId)
          ? s.conversations.map((c) =>
              c.id === conversationId ? { ...c, messages: msgs } : c,
            )
          : [{ id: conversationId, title: msgs[0]?.content.slice(0, 50) || "Conversation", updatedAt: Date.now(), messages: msgs }, ...s.conversations],
      }));
    }
    setActiveConversation(conversationId);
  }, [backendQuery.data, conversationId]);

  useEffect(() => {
    setActiveConversation(conversationId);
  }, [conversationId]);

  const activeConversation = chat.conversations.find((c) => c.id === conversationId);

  // ``isNearBottom`` drives both the auto-scroll behavior and the
  // floating button visibility. Default ``true`` so a fresh open
  // sticks to the latest message; user scrolling up flips it false
  // and the auto-scroll-on-token-append stops fighting them.
  const [isNearBottom, setIsNearBottom] = useState(true);

  function scrollToBottom(behavior: ScrollBehavior = "smooth") {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior });
  }

  // Scroll listener: keep ``isNearBottom`` in sync with the user's
  // scroll position. ``passive`` so the listener can't accidentally
  // cancel the scroll, and re-bound on conversation change so
  // navigating between threads doesn't carry stale state.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    function update() {
      const target = scrollRef.current;
      if (!target) return;
      const distance =
        target.scrollHeight - target.scrollTop - target.clientHeight;
      setIsNearBottom(distance <= NEAR_BOTTOM_THRESHOLD);
    }
    update();
    node.addEventListener("scroll", update, { passive: true });
    return () => node.removeEventListener("scroll", update);
  }, [conversationId]);

  // Reset bottom-stickiness on conversation change. The route
  // component doesn't unmount when navigating between
  // ``/chat/A`` -> ``/chat/B`` (same route shape), so without this
  // the previous thread's ``isNearBottom = false`` (e.g. after the
  // user scrolled up) leaks into the new thread, the auto-scroll
  // effect refuses to jump, and the user lands mid-thread with the
  // floating button visible instead of at the latest turn. The
  // ``rAF`` defers the scroll until after the new messages have
  // rendered into the DOM so ``scrollHeight`` is the real height,
  // not the previous thread's.
  useEffect(() => {
    setIsNearBottom(true);
    const handle = requestAnimationFrame(() => scrollToBottom("auto"));
    return () => cancelAnimationFrame(handle);
  }, [conversationId]);

  // Auto-scroll on message append / streaming, but only when the user
  // was already at the bottom. If they've scrolled up to read older
  // turns, the floating button is the way back -- we don't yank them.
  useEffect(() => {
    if (isNearBottom) {
      scrollToBottom("auto");
    }
  }, [
    activeConversation?.messages.length,
    chat.isStreaming,
    chat.streamingContent,
    isNearBottom,
  ]);

  async function handleSend(msg: string) {
    setActiveConversation(conversationId);
    const backendId = await chat.sendMessage(msg, scope);
    if (backendId && backendId !== conversationId) {
      navigate({ to: "/chat/$conversationId", params: { conversationId: backendId } });
    }
  }

  const isLoadingFromBackend = backendQuery.isLoading && !localConversation;
  const hasMessages = activeConversation && activeConversation.messages.length > 0;
  const isActiveStreaming = chat.isStreaming && chat.activeConversationId === conversationId;

  return (
    <div className="flex h-[calc(100vh-3rem)]">
      <ConversationList
        conversations={chat.conversations}
        activeId={conversationId}
        onNew={() => navigate({ to: "/chat" })}
        onSearch={() => palette.setOpen(true)}
        onDelete={(id) => {
          deleteMutation.mutate(id);
          if (id === conversationId) navigate({ to: "/chat" });
        }}
      />

      <ConversationCommandPalette
        open={palette.open}
        onOpenChange={palette.setOpen}
        conversations={chat.conversations}
        onNew={() => navigate({ to: "/chat" })}
      />

      <div className="flex flex-col flex-1 min-w-0 bg-[#fafaf9] dark:bg-[#131315]">
        <div className="border-b border-zinc-200/60 dark:border-zinc-700/30 bg-white/60 dark:bg-zinc-900/40 px-4 py-2">
          <button
            type="button"
            onClick={() => setScopeOpen((v) => !v)}
            className="text-[11px] font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
          >
            {scope.org_id
              ? `Scope: org pinned · ${scope.team_ids.length} team(s) · ${scope.service_ids.length} service(s) ${scopeOpen ? "−" : "+"}`
              : `Scope: whole corpus ${scopeOpen ? "−" : "+"}`}
          </button>
          {scopeOpen && (
            <div className="mt-3">
              <ScopeSelector value={scope} onChange={setScope} compact />
            </div>
          )}
        </div>
        {isLoadingFromBackend ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        ) : hasMessages ? (
          <>
            {/* Wrapping the scroll area in a ``relative`` container so
                the floating "scroll to bottom" button can position
                itself against the messages region rather than the
                whole page. The button only renders while the user is
                scrolled away from the bottom -- otherwise it would
                obscure content for no reason. */}
            <div className="relative flex-1 min-h-0">
              <div ref={scrollRef} className="absolute inset-0 overflow-y-auto">
                <div className="max-w-[42rem] mx-auto px-4 py-6 space-y-1">
                  {activeConversation.messages.map((msg) => (
                    <ChatMessage key={msg.id} message={msg} />
                  ))}

                  {isActiveStreaming && chat.streamingContent && (
                    <ChatMessage
                      streaming
                      message={{
                        id: "__streaming__",
                        role: "assistant",
                        content: chat.streamingContent,
                        citations: chat.streamingCitations,
                        timestamp: Date.now(),
                      }}
                    />
                  )}

                  {isActiveStreaming && !chat.streamingContent && (
                    <div className="py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce" style={{ animationDelay: "150ms" }} />
                        <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {!isNearBottom && (
                <button
                  type="button"
                  onClick={() => scrollToBottom("smooth")}
                  aria-label="Scroll to latest message"
                  title="Scroll to latest"
                  className="
                    absolute bottom-4 left-1/2 -translate-x-1/2 z-10
                    flex items-center gap-1.5
                    rounded-full border border-zinc-200 dark:border-zinc-700/60
                    bg-white/95 dark:bg-zinc-900/95 backdrop-blur
                    px-3 py-1.5 text-[11px] font-medium
                    text-zinc-600 dark:text-zinc-300
                    shadow-md
                    hover:bg-zinc-50 dark:hover:bg-zinc-800
                    focus-visible:outline-none focus-visible:ring-2
                    focus-visible:ring-[var(--color-accent)]
                    dark:focus-visible:ring-[var(--color-accent-dark)]
                    transition-colors
                  "
                >
                  <ArrowDown className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Scroll to latest</span>
                </button>
              )}
            </div>

            <ChatInput
              onSend={handleSend}
              disabled={chat.isStreaming}
            />
          </>
        ) : (
          <>
            <div className="flex-1" />
            <ChatInput
              onSend={handleSend}
              disabled={chat.isStreaming}
            />
          </>
        )}
      </div>
    </div>
  );
}
