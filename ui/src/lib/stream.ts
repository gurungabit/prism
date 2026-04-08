import { SSEEventSchema, type SSEEvent } from "./schemas";
import { streamUrl } from "./api";

export type StreamStatus = "connecting" | "connected" | "reconnecting" | "closed" | "error";

export interface StreamConnection {
  close: () => void;
}

/**
 * Connect to the analysis SSE stream. Calls `onEvent` for each parsed event,
 * `onStatus` when the connection status changes. Handles auto-reconnection
 * with exponential backoff.
 */
export function connectStream(
  analysisId: string,
  callbacks: {
    onEvent: (event: SSEEvent) => void;
    onStatus: (status: StreamStatus) => void;
    onError?: (error: string) => void;
  },
): StreamConnection {
  let eventSource: EventSource | null = null;
  let retryCount = 0;
  let closed = false;
  let retryTimeout: ReturnType<typeof setTimeout> | null = null;

  function connect() {
    if (closed) return;

    const url = streamUrl(analysisId);
    callbacks.onStatus(retryCount > 0 ? "reconnecting" : "connecting");

    eventSource = new EventSource(url);

    eventSource.onopen = () => {
      retryCount = 0;
      callbacks.onStatus("connected");
    };

    eventSource.onmessage = (msg) => {
      try {
        const raw = JSON.parse(msg.data);
        const parsed = SSEEventSchema.safeParse(raw);

        if (parsed.success) {
          callbacks.onEvent(parsed.data);

          if (parsed.data.type === "complete" || parsed.data.type === "error") {
            close();
          }
        }
      } catch {
        // keepalive or malformed — ignore
      }
    };

    eventSource.onerror = () => {
      if (closed) return;

      eventSource?.close();
      eventSource = null;

      if (retryCount >= 5) {
        callbacks.onStatus("error");
        callbacks.onError?.("Connection lost after multiple retries");
        return;
      }

      retryCount++;
      const delay = Math.min(1000 * 2 ** retryCount, 15000);
      callbacks.onStatus("reconnecting");
      retryTimeout = setTimeout(connect, delay);
    };
  }

  function close() {
    closed = true;
    if (retryTimeout) clearTimeout(retryTimeout);
    eventSource?.close();
    eventSource = null;
    callbacks.onStatus("closed");
  }

  connect();

  return { close };
}
