import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useChat, useConversations, useDeleteConversation } from "../hooks/useChat";
import { useChatStore } from "../stores/chat";
import { ConversationList } from "../components/chat/ConversationList";
import { ChatInput } from "../components/chat/ChatInput";
import {
  Search,
  GitBranch,
  AlertTriangle,
  FileText,
} from "lucide-react";

export function ChatPage() {
  const chat = useChat();
  const navigate = useNavigate();
  const conversationsQuery = useConversations();
  const deleteMutation = useDeleteConversation();

  useEffect(() => {
    useChatStore.getState().setActiveConversation(null);
  }, []);

  useEffect(() => {
    if (conversationsQuery.data?.conversations) {
      chat.loadFromBackend(conversationsQuery.data.conversations);
    }
  }, [conversationsQuery.data]);

  const suggestions = [
    { icon: <Search className="w-4 h-4" />, text: "What teams own the checkout service?" },
    { icon: <AlertTriangle className="w-4 h-4" />, text: "Show me recent pipeline failures" },
    { icon: <GitBranch className="w-4 h-4" />, text: "Which services have ownership conflicts?" },
    { icon: <FileText className="w-4 h-4" />, text: "What docs exist for the auth system?" },
  ];

  async function handleSend(msg: string) {
    if (!useChatStore.getState().activeConversationId) {
      chat.createConversation();
    }
    const convId = useChatStore.getState().activeConversationId;
    if (!convId) return;
    navigate({ to: "/chat/$conversationId", params: { conversationId: convId } });
    chat.sendMessage(msg);
  }

  function handleNew() {
    chat.setActiveConversation(null);
  }

  return (
    <div className="flex h-[calc(100vh-3rem)]">
      <ConversationList
        conversations={chat.conversations}
        activeId={null}
        onNew={handleNew}
        onDelete={(id) => deleteMutation.mutate(id)}
      />

      <div className="flex flex-col flex-1 min-w-0 bg-[#fafaf9] dark:bg-[#131315]">
        <div className="flex-1 flex flex-col items-center justify-center px-6">
          <h2 className="text-xl font-semibold text-zinc-800 dark:text-zinc-200 mb-8 tracking-tight">
            What do you want to know?
          </h2>

          <div className="grid grid-cols-2 gap-2 w-full max-w-md">
            {suggestions.map((s) => (
              <button
                key={s.text}
                onClick={() => handleSend(s.text)}
                className="flex items-start gap-2.5 p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-700/40 text-left text-[12px] text-zinc-500 dark:text-zinc-400 hover:border-zinc-300 dark:hover:border-zinc-600/60 hover:text-zinc-700 dark:hover:text-zinc-300 transition-all duration-150 leading-snug"
              >
                <span className="text-zinc-300 dark:text-zinc-600 mt-0.5 shrink-0">
                  {s.icon}
                </span>
                <span>{s.text}</span>
              </button>
            ))}
          </div>
        </div>

        <ChatInput
          onSend={handleSend}
          disabled={chat.isStreaming}
        />
      </div>
    </div>
  );
}
