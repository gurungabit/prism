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
  // Lightweight last-message preview from the backend list endpoint.
  // Hydrated alongside ``messages`` for current-session chats but
  // available for backend-restored conversations whose full
  // ``messages`` array hasn't been loaded yet. Used by both the
  // sidebar preview and the command-palette substring search -- the
  // previous version only inspected ``messages[last]``, which is
  // empty until a conversation is opened, so backend-loaded
  // conversations were invisible to search.
  lastMessage?: string;
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
  loadFromBackend: (
    backendConversations: Array<{
      conversation_id: string;
      preview: string;
      last_message: string;
      // Wall-clock seconds (UNIX) of the most recent commit. Optional
      // because the backend skips it for conversations without a
      // recorded timestamp -- the hydrate path falls back to ``Date.now()``.
      updated_at?: number | null;
    }>,
  ) => void;
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
      const newConversations: Conversation[] = backendConversations
        .filter((bc) => !existingIds.has(bc.conversation_id))
        .map((bc) => ({
          id: bc.conversation_id,
          title: bc.preview || "Conversation",
          // ``updated_at`` is UNIX seconds; the store keeps ms. Fall
          // back to ``Date.now()`` only if the backend didn't record
          // one (e.g. legacy state pre-rounds-of-fixes) -- previously
          // we always used ``Date.now()``, which made the palette
          // bucket every backend-loaded conversation as "Today".
          updatedAt:
            typeof bc.updated_at === "number"
              ? bc.updated_at * 1000
              : Date.now(),
          lastMessage: bc.last_message || undefined,
          messages: [],
        }));
      return { conversations: [...newConversations, ...s.conversations] };
    }),
}));
