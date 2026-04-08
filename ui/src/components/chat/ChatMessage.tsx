import { Children, type AnchorHTMLAttributes, type ClassAttributes, type ComponentProps, type ReactNode } from "react";
import { Streamdown } from "streamdown";
import type { ChatMessage as ChatMessageType } from "../../stores/chat";
import { SourceCitation } from "./SourceCitation";

interface ChatMessageProps {
  message: ChatMessageType;
  streaming?: boolean;
}

type SourceLinkProps =
  ClassAttributes<HTMLAnchorElement> &
  AnchorHTMLAttributes<HTMLAnchorElement> & {
    children?: ReactNode;
  };

function expandSourceRange(start: number, end: number) {
  const values: number[] = [];
  const lower = Math.min(start, end);
  const upper = Math.max(start, end);
  for (let index = lower; index <= upper; index += 1) {
    values.push(index);
  }
  return values;
}

function sourceReferenceMarkdown(content: string) {
  return content.replace(
    /\[(Source\s+(\d+)(?:\s*-\s*(\d+))?)\](?!\()/gi,
    (_match, label: string, start: string, end?: string) =>
      `[${label}](/__source__/${start}${end ? `-${end}` : ""})`,
  );
}

function textFromNode(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number") {
        return String(child);
      }
      if (
        child &&
        typeof child === "object" &&
        "props" in child &&
        child.props &&
        typeof child.props === "object" &&
        "children" in child.props
      ) {
        return textFromNode(child.props.children as ReactNode);
      }
      return "";
    })
    .join("");
}

export function ChatMessage({ message, streaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";
  const citations = [...(message.citations ?? [])].sort((a, b) => a.index - b.index);
  const citationMap = new Map(citations.map((citation) => [citation.index, citation]));

  const transformedContent = sourceReferenceMarkdown(message.content);

  const SourceLink = ({ href, children }: SourceLinkProps) => {
    const label = textFromNode(children) || "Source";

    if (typeof href === "string" && href.startsWith("/__source__/")) {
      const match = href.match(/^\/__source__\/(\d+)(?:-(\d+))?$/i);
      const start = Number(match?.[1] ?? 0);
      const end = Number(match?.[2] ?? match?.[1] ?? 0);
      const selectedCitations = expandSourceRange(start, end)
        .map((index) => citationMap.get(index))
        .filter((citation): citation is NonNullable<typeof citation> => Boolean(citation));

      if (selectedCitations.length > 0) {
        return (
          <SourceCitation
            label={label || `Source ${start}`}
            citations={selectedCitations}
          />
        );
      }

      return (
        <SourceCitation
          label={label || `Source ${start}`}
          citations={[]}
          emptyMessage="Source details are unavailable for this older message. Ask the question again and the new answer will include clickable source chunks."
        />
      );
    }

    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-[var(--color-accent)] underline decoration-[var(--color-accent-subtle)] underline-offset-2 hover:opacity-80 dark:text-[var(--color-accent-dark)]"
      >
        {children}
      </a>
    );
  };

  const streamdownComponents = {
    a: SourceLink,
  } as NonNullable<ComponentProps<typeof Streamdown>["components"]>;

  return (
    <div className={`group py-3 ${isUser ? "flex justify-end" : ""}`}>
      <div className={isUser ? "max-w-[75%]" : "max-w-none"}>
        {isUser ? (
          <div className="bg-zinc-100 dark:bg-zinc-700/40 rounded-2xl rounded-br-md px-4 py-2.5 text-[13px] text-zinc-800 dark:text-zinc-200 leading-relaxed whitespace-pre-wrap">
            {message.content}
          </div>
        ) : (
          <div className="prose-chat text-[13px] text-zinc-700 dark:text-zinc-300 leading-[1.7]">
            <Streamdown
              mode={streaming ? "streaming" : "static"}
              components={streamdownComponents}
            >
              {transformedContent}
            </Streamdown>

            {citations.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-zinc-100 pt-3 dark:border-zinc-700/40">
                <div className="space-y-1">
                  <span className="block text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                    Retrieved Sources
                  </span>
                  <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                    Click any source to inspect the retrieved chunk behind this answer.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {citations.map((citation) => (
                    <SourceCitation
                      key={citation.index}
                      label={`Source ${citation.index}`}
                      citations={[citation]}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
