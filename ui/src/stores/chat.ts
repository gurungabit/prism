import { create } from "zustand";

export interface ChatCitation {
  index: number;
  title: string;
  platform: string;
  source_path: string;
  source_url?: string;
  section_heading?: string;
  score?: number;
  content?: string;
  excerpt?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  // ``kind`` distinguishes ordinary assistant text from typed
  // outage events the backend now emits as SSE ``error`` events
  // (``retrieval_unavailable``, ``llm_unavailable``). Without this
  // tag the UI used to render the outage as plain assistant prose,
  // making infrastructure failures look like model output.
  kind?: "answer" | "error";
  errorCode?: string;
  content: string;
  citations?: ChatCitation[];
  timestamp: number;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
}

interface ChatState {
  activeConversationId: string | null;
  conversations: Conversation[];
  streamingContent: string;
  streamingCitations: ChatCitation[];
  isStreaming: boolean;

  setActiveConversation: (id: string | null) => void;
  addConversation: (conv: Conversation) => void;
  addMessage: (conversationId: string, message: ChatMessage) => void;
  appendStreamToken: (token: string) => void;
  setStreamingCitations: (citations: ChatCitation[]) => void;
  finalizeStream: (conversationId: string) => void;
  setStreaming: (streaming: boolean) => void;
  deleteConversation: (id: string) => void;
  updateConversationId: (oldId: string, newId: string) => void;
  loadFromBackend: (backendConversations: Array<{ conversation_id: string; preview: string; last_message: string }>) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  activeConversationId: null,
  conversations: [],
  streamingContent: "",
  streamingCitations: [],
  isStreaming: false,

  setActiveConversation: (id) => set({ activeConversationId: id }),

  addConversation: (conv) =>
    set((s) => {
      if (s.conversations.some((c) => c.id === conv.id)) return s;
      return { conversations: [conv, ...s.conversations] };
    }),

  addMessage: (conversationId, message) =>
    set((s) => ({
      conversations: s.conversations.map((c) => {
        if (c.id !== conversationId) return c;
        const title = c.messages.length === 0 && message.role === "user"
          ? message.content.slice(0, 50)
          : c.title;
        return { ...c, title, messages: [...c.messages, message], updatedAt: Date.now() };
      }),
    })),

  appendStreamToken: (token) =>
    set((s) => ({ streamingContent: s.streamingContent + token })),

  setStreamingCitations: (citations) =>
    set({ streamingCitations: citations }),

  finalizeStream: (conversationId) => {
    const { streamingContent, streamingCitations } = get();
    if (!streamingContent) return;

    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: streamingContent,
      citations: streamingCitations,
      timestamp: Date.now(),
    };

    set((s) => ({
      streamingContent: "",
      streamingCitations: [],
      isStreaming: false,
      conversations: s.conversations.map((c) =>
        c.id === conversationId
          ? { ...c, messages: [...c.messages, message], updatedAt: Date.now() }
          : c,
      ),
    }));
  },

  setStreaming: (streaming) =>
    set({
      isStreaming: streaming,
      streamingContent: "",
      streamingCitations: [],
    }),

  deleteConversation: (id) =>
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      activeConversationId: s.activeConversationId === id ? null : s.activeConversationId,
    })),

  updateConversationId: (oldId, newId) =>
    set((s) => ({
      activeConversationId: s.activeConversationId === oldId ? newId : s.activeConversationId,
      conversations: s.conversations.map((c) =>
        c.id === oldId ? { ...c, id: newId } : c,
      ),
    })),

  loadFromBackend: (backendConversations) =>
    set((s) => {
      const existingIds = new Set(s.conversations.map((c) => c.id));
      const newConversations = backendConversations
        .filter((bc) => !existingIds.has(bc.conversation_id))
        .map((bc) => ({
          id: bc.conversation_id,
          title: bc.preview || "Conversation",
          updatedAt: Date.now(),
          messages: [],
        }));
      return { conversations: [...newConversations, ...s.conversations] };
    }),
}));
