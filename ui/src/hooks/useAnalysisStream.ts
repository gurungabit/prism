import { useCallback, useEffect, useRef } from "react";
import { useAnalysisStore } from "../stores/analysis";
import { connectStream, type StreamConnection } from "../lib/stream";
import type { SSEEvent } from "../lib/schemas";

export function useAnalysisStream() {
  const store = useAnalysisStore();
  const connectionRef = useRef<StreamConnection | null>(null);

  const handleEvent = useCallback(
    (event: SSEEvent) => {
      switch (event.type) {
        case "agent_step":
          store.addAgentStep(event);
          break;
        case "complete":
          if (event.report) {
            store.setReport(event.report);
          }
          if (event.error) {
            store.setError(event.error);
          }
          break;
        case "error":
          store.setError(event.error);
          break;
      }
    },
    [store],
  );

  const connect = useCallback(
    (runId: string) => {
      connectionRef.current?.close();
      store.startRun(runId);

      connectionRef.current = connectStream(runId, {
        onEvent: handleEvent,
        onStatus: (status) => store.setStreamStatus(status),
        onError: (err) => store.setError(err),
      });
    },
    [handleEvent, store],
  );

  const disconnect = useCallback(() => {
    connectionRef.current?.close();
    connectionRef.current = null;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      connectionRef.current?.close();
    };
  }, []);

  return { connect, disconnect, ...store };
}
