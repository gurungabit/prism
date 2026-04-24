import { useCallback, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  ControlButton,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type EdgeMouseHandler,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { ArrowLeft, ArrowRight, Maximize2, Minimize2, Users, X } from "lucide-react";

import "@xyflow/react/dist/style.css";
import type { PRISMReport } from "../../lib/schemas";
import { useFullscreen } from "../../hooks/useFullscreen";

type TeamEdge = NonNullable<PRISMReport["team_blast_radius"]>["upstream"][number];

type Direction = "upstream" | "downstream";

interface BlastRadiusGraphProps {
  primaryTeamName: string;
  upstream: TeamEdge[];
  downstream: TeamEdge[];
  // Map doc path -> clickable URL (already wired via the linkify path on the
  // analyze page).
  urlByPath?: Record<string, string>;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 64;

type PrimaryNodeData = { label: string; [k: string]: unknown };
type TeamNodeData = {
  label: string;
  relationship: TeamEdge["relationship"];
  direction: Direction;
  [k: string]: unknown;
};

function PrimaryNode({ data }: NodeProps<Node<PrimaryNodeData>>) {
  return (
    <div className="w-[180px] rounded-lg border-2 border-[var(--color-accent)] dark:border-[var(--color-accent-dark)] bg-[var(--color-accent)]/10 dark:bg-[var(--color-accent-dark)]/15 px-3 py-2.5 text-center">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]">
        Primary
      </div>
      <div className="text-[13px] font-semibold text-zinc-900 dark:text-zinc-100 mt-0.5 truncate">
        {data.label}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-400" />
      <Handle type="target" position={Position.Left} className="!bg-zinc-400" />
    </div>
  );
}

function TeamNode({ data }: NodeProps<Node<TeamNodeData>>) {
  const badgeColor =
    data.relationship === "blocking"
      ? "text-rose-700 dark:text-rose-300 bg-rose-100 dark:bg-rose-950/40"
      : data.relationship === "impacted"
        ? "text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-950/40"
        : "text-zinc-600 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800/50";

  return (
    <div className="w-[180px] rounded-lg border border-zinc-200 dark:border-zinc-700/60 bg-white dark:bg-[#1e1e20] px-3 py-2.5 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/60 transition">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
        <Users className="w-3 h-3" />
        {data.direction === "upstream" ? "Upstream" : "Downstream"}
      </div>
      <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 mt-0.5 truncate">
        {data.label}
      </div>
      <span
        className={`inline-block mt-1 px-1.5 py-0.5 rounded text-[9px] font-medium uppercase tracking-wider ${badgeColor}`}
      >
        {data.relationship}
      </span>
      <Handle type="target" position={Position.Left} className="!bg-zinc-400" />
      <Handle type="source" position={Position.Right} className="!bg-zinc-400" />
    </div>
  );
}

const nodeTypes = { primary: PrimaryNode, team: TeamNode };

function layoutWithDagre(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 120 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const edge of edges) g.setEdge(edge.source, edge.target);

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

export function BlastRadiusGraph({
  primaryTeamName,
  upstream,
  downstream,
  urlByPath = {},
}: BlastRadiusGraphProps) {
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const { ref: fullscreenRef, isFullscreen, toggle: toggleFullscreen } = useFullscreen();

  const { nodes, edges, edgeMap } = useMemo(() => {
    const nodeList: Node[] = [
      {
        id: "primary",
        type: "primary",
        position: { x: 0, y: 0 },
        data: { label: primaryTeamName },
      },
    ];
    const edgeList: Edge[] = [];
    const edgeInfo: Record<string, { direction: Direction; team: TeamEdge }> = {};

    const addEdge = (direction: Direction, team: TeamEdge, index: number) => {
      const nodeId = `${direction}-${index}`;
      nodeList.push({
        id: nodeId,
        type: "team",
        position: { x: 0, y: 0 },
        data: {
          label: team.team_name,
          relationship: team.relationship,
          direction,
        },
      });
      const edgeId = `e-${direction}-${index}`;
      const strokeColor =
        team.relationship === "blocking"
          ? "rgb(244 63 94)"
          : team.relationship === "impacted"
            ? "rgb(245 158 11)"
            : "rgb(113 113 122)";
      edgeList.push({
        id: edgeId,
        source: direction === "upstream" ? nodeId : "primary",
        target: direction === "upstream" ? "primary" : nodeId,
        type: "smoothstep",
        animated: team.relationship === "blocking",
        label: team.relationship,
        labelStyle: { fontSize: 10, fill: strokeColor },
        labelBgStyle: { fill: "rgb(24 24 27 / 0.85)" },
        style: { stroke: strokeColor, strokeWidth: 1.75 },
      });
      edgeInfo[edgeId] = { direction, team };
    };

    upstream.forEach((t, i) => addEdge("upstream", t, i));
    downstream.forEach((t, i) => addEdge("downstream", t, i));

    return {
      nodes: layoutWithDagre(nodeList, edgeList),
      edges: edgeList,
      edgeMap: edgeInfo,
    };
  }, [primaryTeamName, upstream, downstream]);

  const onEdgeClick = useCallback<EdgeMouseHandler>((_event, edge) => {
    setSelectedEdgeId(edge.id);
  }, []);

  const onNodeClick = useCallback(
    (_event: unknown, node: Node) => {
      if (node.id === "primary") return;
      // Tapping a team node is equivalent to tapping its edge.
      const edgeId = Object.keys(edgeMap).find(
        (id) => edgeMap[id]!.direction + "-" + node.id.split("-")[1] === node.id,
      );
      if (edgeId) setSelectedEdgeId(edgeId);
    },
    [edgeMap],
  );

  const selected = selectedEdgeId ? edgeMap[selectedEdgeId] : null;

  const hasTeams = upstream.length > 0 || downstream.length > 0;
  if (!hasTeams) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-200 dark:border-zinc-700/50 p-6 text-center text-[12px] text-zinc-400 dark:text-zinc-500">
        No team-level dependencies identified for this requirement.
      </div>
    );
  }

  return (
    <div
      ref={fullscreenRef}
      className={`relative w-full ${isFullscreen ? "h-screen rounded-none border-0" : "h-[360px] rounded-lg border border-zinc-200 dark:border-zinc-700/40"} bg-white dark:bg-[#171719] overflow-hidden`}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onEdgeClick={onEdgeClick}
        onNodeClick={onNodeClick}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={2}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgb(113 113 122 / 0.2)" />
        <Controls
          showInteractive={false}
          className="!bg-white/80 dark:!bg-zinc-800/80 !border-zinc-200 dark:!border-zinc-700/40"
        >
          <ControlButton
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            aria-label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? <Minimize2 /> : <Maximize2 />}
          </ControlButton>
        </Controls>
      </ReactFlow>

      {selected && (
        <EdgeDetailCard
          direction={selected.direction}
          team={selected.team}
          urlByPath={urlByPath}
          onClose={() => setSelectedEdgeId(null)}
        />
      )}
    </div>
  );
}

function EdgeDetailCard({
  direction,
  team,
  urlByPath,
  onClose,
}: {
  direction: Direction;
  team: TeamEdge;
  urlByPath: Record<string, string>;
  onClose: () => void;
}) {
  const arrow =
    direction === "upstream" ? (
      <ArrowLeft className="w-3.5 h-3.5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
    ) : (
      <ArrowRight className="w-3.5 h-3.5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
    );

  return (
    <aside className="absolute top-3 right-3 w-[300px] max-w-[90%] rounded-lg border border-zinc-200 dark:border-zinc-700/60 bg-white dark:bg-[#1e1e20] shadow-lg overflow-hidden">
      <div className="flex items-start justify-between gap-2 px-3 py-2 border-b border-zinc-200/80 dark:border-zinc-700/40">
        <div className="flex items-center gap-1.5 min-w-0">
          {arrow}
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            {direction}
          </span>
          <span className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 truncate">
            {team.team_name}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
          aria-label="Close"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="px-3 py-2.5 space-y-2.5 text-[12px]">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-0.5">
            Relationship
          </div>
          <span
            className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${
              team.relationship === "blocking"
                ? "text-rose-700 dark:text-rose-300 bg-rose-100 dark:bg-rose-950/40"
                : team.relationship === "impacted"
                  ? "text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-950/40"
                  : "text-zinc-600 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800/50"
            }`}
          >
            {team.relationship}
          </span>
        </div>

        {team.reason && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-0.5">
              Why
            </div>
            <p className="text-zinc-700 dark:text-zinc-300 leading-relaxed">
              {team.reason}
            </p>
          </div>
        )}

        {team.evidence_services.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-0.5">
              Evidence services
            </div>
            <div className="flex flex-wrap gap-1">
              {team.evidence_services.map((svc) => (
                <span
                  key={svc}
                  className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800/60 text-zinc-600 dark:text-zinc-300"
                >
                  {svc}
                </span>
              ))}
            </div>
          </div>
        )}

        {team.sources.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-0.5">
              Sources
            </div>
            <div className="space-y-1">
              {team.sources.map((s, i) => {
                const href =
                  s.source_url || urlByPath[s.document_path] || "";
                const label = s.document_path || "(no path)";
                return href ? (
                  <a
                    key={i}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block font-mono text-[11px] text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline break-all"
                  >
                    {label}
                  </a>
                ) : (
                  <span
                    key={i}
                    className="block font-mono text-[11px] text-zinc-500 dark:text-zinc-400 break-all"
                  >
                    {label}
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
