import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useChatStore, type ChatMessage, type Conversation, type ChatCitation } from "../stores/chat";
import { getConversations, getConversation, deleteConversation as apiDeleteConversation, type ChatConversation } from "../lib/api";

const BASE_URL = import.meta.env.VITE_API_URL || "";

export function useChat() {
  const store = useChatStore();

  function createConversation(title?: string): Conversation {
    const conv: Conversation = {
      id: crypto.randomUUID(),
      title: title || "New conversation",
      updatedAt: Date.now(),
      messages: [],
    };
    store.addConversation(conv);
    store.setActiveConversation(conv.id);
    return conv;
  }

  async function sendMessage(content: string): Promise<string | null> {
    const convId = useChatStore.getState().activeConversationId;
    if (!convId) return null;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      timestamp: Date.now(),
    };
    store.addMessage(convId, userMsg);
    store.setStreaming(true);

    let backendConvId: string | null = null;

    try {
      const res = await fetch(`${BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: content, conversation_id: convId }),
      });

      if (!res.ok) throw new Error(`Chat API error: ${res.status}`);
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const dataStr = line.startsWith("data: ") ? line.slice(6) : line.slice(5);
            if (!dataStr) continue;
            try {
              const parsed: Record<string, unknown> = JSON.parse(dataStr);
              if (
                currentEvent === "metadata" &&
                typeof parsed.conversation_id === "string"
              ) {
                backendConvId = parsed.conversation_id;
                store.updateConversationId(convId, backendConvId);
                if (Array.isArray(parsed.citations)) {
                  const citations = parsed.citations
                    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
                    .map(
                      (item): ChatCitation => ({
                        index: Number(item.index ?? 0),
                        title: String(item.title ?? item.source_path ?? "Source"),
                        platform: String(item.platform ?? ""),
                        source_path: String(item.source_path ?? ""),
                        source_url: typeof item.source_url === "string" ? item.source_url : undefined,
                        section_heading: typeof item.section_heading === "string" ? item.section_heading : undefined,
                        score: typeof item.score === "number" ? item.score : undefined,
                        content: typeof item.content === "string" ? item.content : undefined,
                        excerpt: typeof item.excerpt === "string" ? item.excerpt : undefined,
                      }),
                    )
                    .filter((citation) => citation.index > 0 && citation.source_path);
                  store.setStreamingCitations(citations);
                }
              } else if (
                currentEvent === "token" &&
                typeof parsed.content === "string"
              ) {
                store.appendStreamToken(parsed.content);
              } else if (
                currentEvent === "" &&
                typeof parsed.content === "string"
              ) {
                store.appendStreamToken(parsed.content);
              }
            } catch {
              // skip malformed SSE data
            }
          } else if (line === "") {
            currentEvent = "";
          }
        }
      }

      const finalId = backendConvId ?? convId;
      store.finalizeStream(finalId);
      return backendConvId;
    } catch (err) {
      const errorContent = err instanceof Error ? err.message : "Unknown error";
      const activeId = backendConvId ?? convId;
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Error: ${errorContent}`,
        timestamp: Date.now(),
      };
      store.addMessage(activeId, errorMsg);
      return backendConvId;
    } finally {
      store.setStreaming(false);
    }
  }

  return {
    ...store,
    createConversation,
    sendMessage,
  };
}

export function useConversations() {
  return useQuery({
    queryKey: ["chat-conversations"],
    queryFn: () => getConversations(),
    staleTime: 10_000,
  });
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: ["chat-conversation", conversationId],
    queryFn: () => getConversation(conversationId!),
    enabled: !!conversationId,
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => apiDeleteConversation(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["chat-conversations"] });
      const previous = qc.getQueryData<{ conversations: ChatConversation[] }>(["chat-conversations"]);
      qc.setQueryData<{ conversations: ChatConversation[] }>(["chat-conversations"], (old) =>
        old ? { conversations: old.conversations.filter((c) => c.conversation_id !== id) } : old,
      );
      useChatStore.getState().deleteConversation(id);
      return { previous };
    },
    onError: (_err, _id, context) => {
      if (context?.previous) {
        qc.setQueryData(["chat-conversations"], context.previous);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["chat-conversations"] });
    },
  });
}
