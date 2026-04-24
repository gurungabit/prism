import { useRef, useEffect } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useChat, useConversation, useConversations, useDeleteConversation } from "../hooks/useChat";
import { useChatStore } from "../stores/chat";
import { ConversationList } from "../components/chat/ConversationList";
import { ChatMessage } from "../components/chat/ChatMessage";
import { ChatInput } from "../components/chat/ChatInput";

export function ChatConversationPage() {
  const { conversationId } = useParams({ from: "/chat/$conversationId" });
  const navigate = useNavigate();
  const chat = useChat();
  const deleteMutation = useDeleteConversation();
  const scrollRef = useRef<HTMLDivElement>(null);

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
    const backendId = await chat.sendMessage(msg);
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
