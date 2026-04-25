import { useRef, useEffect, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useChat, useConversation, useConversations, useDeleteConversation } from "../hooks/useChat";
import { useChatStore } from "../stores/chat";
import { ConversationList } from "../components/chat/ConversationList";
import { ChatMessage } from "../components/chat/ChatMessage";
import { ChatInput } from "../components/chat/ChatInput";
import { ScopeSelector, type ScopeValue } from "../components/catalog/ScopeSelector";

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

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeConversation?.messages.length, chat.isStreaming]);

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
        onDelete={(id) => {
          deleteMutation.mutate(id);
          if (id === conversationId) navigate({ to: "/chat" });
        }}
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
            <div ref={scrollRef} className="flex-1 overflow-y-auto">
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
