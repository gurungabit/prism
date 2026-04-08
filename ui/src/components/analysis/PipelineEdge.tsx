interface PipelineEdgeProps {
  fromStatus: string | undefined;
  toStatus: string | undefined;
  vertical?: boolean;
}

function isActive(status: string | undefined) {
  return status === "searching" || status === "reasoning" || status === "verifying";
}

function isDone(status: string | undefined) {
  return status === "complete";
}

export function PipelineEdge({ fromStatus, toStatus, vertical = false }: PipelineEdgeProps) {
  const fromDone = isDone(fromStatus);
  const toActive = isActive(toStatus);
  const toDone = isDone(toStatus);
  const bothDone = fromDone && toDone;
  const flowing = fromDone && toActive;

  const colorClass = bothDone
    ? "text-emerald-400 dark:text-emerald-600"
    : flowing
      ? "text-sky-400 dark:text-sky-500"
      : fromDone
        ? "text-zinc-300 dark:text-zinc-600"
        : "text-zinc-200 dark:text-zinc-700";

  if (vertical) {
    return (
      <div className={`flex flex-col items-center ${colorClass}`}>
        <div className={`w-px h-4 bg-current ${flowing ? "animate-edge-flow" : ""}`} />
        <div className="w-0 h-0 border-l-[3px] border-r-[3px] border-t-[4px] border-transparent border-t-current" />
      </div>
    );
  }

  return (
    <div className={`flex items-center flex-1 min-w-[12px] max-w-[32px] ${colorClass}`}>
      <div className={`flex-1 h-px bg-current ${flowing ? "animate-edge-flow" : ""}`} />
      <div className="w-0 h-0 border-t-[3px] border-b-[3px] border-l-[4px] border-transparent border-l-current flex-shrink-0" />
    </div>
  );
}
