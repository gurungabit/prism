import { useCallback, useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  ControlButton,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { Building2, Boxes, Maximize2, Minimize2, Users } from "lucide-react";

import "@xyflow/react/dist/style.css";
import type { OrganizationGraphResponse } from "../../lib/api";
import { useFullscreen } from "../../hooks/useFullscreen";
import type { SelectedNode } from "./NodeDetailPanel";

// ── layout ────────────────────────────────────────────────────────────────

// xyflow gives us positioning control but no layout algorithm, so we pipe
// through dagre. Picking LR (left-to-right) so the org funnels right into
// teams and services -- matches the natural reading direction of the
// hierarchy.

const NODE_WIDTH = 200;
const NODE_HEIGHT = 64;

function layoutWithDagre(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 80 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      // xyflow uses top-left origin; dagre returns center. Shift by half.
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

// ── custom nodes ──────────────────────────────────────────────────────────

type OrgNodeData = { label: string };
type TeamNodeData = { label: string; description: string };
type ServiceNodeData = { label: string; repo_url: string; description: string };

function OrgNode({ data }: NodeProps<Node<OrgNodeData>>) {
  return (
    <div className="w-[200px] rounded-lg border border-[var(--color-accent)]/60 dark:border-[var(--color-accent-dark)]/60 bg-[var(--color-accent)]/10 dark:bg-[var(--color-accent-dark)]/15 px-3 py-2.5 cursor-pointer hover:brightness-110 transition">
      <div className="flex items-center gap-2">
        <Building2 className="w-3.5 h-3.5 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
        <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]">
          Org
        </div>
      </div>
      <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 mt-1 truncate">
        {data.label}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-400" />
    </div>
  );
}

function TeamNode({ data }: NodeProps<Node<TeamNodeData>>) {
  return (
    <div className="w-[200px] rounded-lg border border-zinc-200 dark:border-zinc-700/60 bg-white dark:bg-[#1e1e20] px-3 py-2.5 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/60 transition">
      <div className="flex items-center gap-2">
        <Users className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Team
        </div>
      </div>
      <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 mt-1 truncate">
        {data.label}
      </div>
      {data.description && (
        <div className="text-[11px] text-zinc-500 dark:text-zinc-500 mt-0.5 truncate">
          {data.description}
        </div>
      )}
      <Handle type="target" position={Position.Left} className="!bg-zinc-400" />
      <Handle type="source" position={Position.Right} className="!bg-zinc-400" />
    </div>
  );
}

function ServiceNode({ data }: NodeProps<Node<ServiceNodeData>>) {
  return (
    <div className="w-[200px] rounded-lg border border-zinc-200 dark:border-zinc-700/60 bg-zinc-50 dark:bg-zinc-800/40 px-3 py-2.5 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-700/50 transition">
      <div className="flex items-center gap-2">
        <Boxes className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500" />
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Service
        </div>
      </div>
      <div className="text-[13px] font-medium text-zinc-900 dark:text-zinc-100 mt-1 truncate">
        {data.label}
      </div>
      {data.description && (
        <div className="text-[11px] text-zinc-500 dark:text-zinc-500 mt-0.5 truncate">
          {data.description}
        </div>
      )}
      <Handle type="target" position={Position.Left} className="!bg-zinc-400" />
      <Handle type="source" position={Position.Right} className="!bg-zinc-400" />
    </div>
  );
}

const nodeTypes = {
  org: OrgNode,
  team: TeamNode,
  service: ServiceNode,
};

// ── graph builder ─────────────────────────────────────────────────────────

interface OrganizationGraphProps {
  data: OrganizationGraphResponse;
  onSelect: (selected: SelectedNode) => void;
}

export function OrganizationGraph({ data, onSelect }: OrganizationGraphProps) {
  const { ref: fullscreenRef, isFullscreen, toggle: toggleFullscreen } = useFullscreen();

  // Click handler dispatches on node id prefix. Node ids are stable
  // (``<kind>-<uuid>``) because we construct them below, so string split is
  // cheap and safer than threading detail routes into node data.
  const handleNodeClick = useCallback<NodeMouseHandler>(
    (_event, node) => {
      // UUIDs contain dashes, so join everything after the kind prefix.
      const dashIdx = node.id.indexOf("-");
      if (dashIdx === -1) return;
      const kind = node.id.slice(0, dashIdx);
      const id = node.id.slice(dashIdx + 1);
      if (!id) return;
      if (kind === "org") onSelect({ kind: "org", id });
      else if (kind === "team") onSelect({ kind: "team", id });
      else if (kind === "svc") onSelect({ kind: "service", id });
    },
    [onSelect],
  );

  const { nodes, edges } = useMemo(() => {
    const nodeList: Node[] = [];
    const edgeList: Edge[] = [];

    // Hierarchy: org -> team -> service. We emit the tree edges here and then
    // add dependency edges (dashed) as a second pass so the layout still
    // ranks by hierarchy.
    for (const org of data.orgs) {
      nodeList.push({
        id: `org-${org.id}`,
        type: "org",
        position: { x: 0, y: 0 },
        data: { label: org.name },
      });
    }

    for (const team of data.teams) {
      nodeList.push({
        id: `team-${team.id}`,
        type: "team",
        position: { x: 0, y: 0 },
        data: { label: team.name, description: team.description ?? "" },
      });
      edgeList.push({
        id: `e-org-${team.org_id}-team-${team.id}`,
        source: `org-${team.org_id}`,
        target: `team-${team.id}`,
        type: "smoothstep",
        animated: false,
        style: { stroke: "rgb(113 113 122 / 0.5)", strokeWidth: 1.5 },
      });
    }

    for (const svc of data.services) {
      nodeList.push({
        id: `svc-${svc.id}`,
        type: "service",
        position: { x: 0, y: 0 },
        data: {
          label: svc.name,
          repo_url: svc.repo_url ?? "",
          description: svc.description ?? "",
        },
      });
      edgeList.push({
        id: `e-team-${svc.team_id}-svc-${svc.id}`,
        source: `team-${svc.team_id}`,
        target: `svc-${svc.id}`,
        type: "smoothstep",
        animated: false,
        style: { stroke: "rgb(113 113 122 / 0.5)", strokeWidth: 1.5 },
      });
    }

    for (const dep of data.dependencies) {
      edgeList.push({
        id: `dep-${dep.from_service_id}-${dep.to_service_id}`,
        source: `svc-${dep.from_service_id}`,
        target: `svc-${dep.to_service_id}`,
        type: "smoothstep",
        animated: true,
        label: "depends on",
        labelStyle: { fontSize: 10, fill: "rgb(161 161 170)" },
        labelBgStyle: { fill: "rgb(24 24 27 / 0.7)" },
        style: {
          stroke: "var(--color-accent)",
          strokeWidth: 1.5,
          strokeDasharray: "4 4",
        },
      });
    }

    // Only layout if both sides of every edge exist -- dagre chokes on
    // dangling edges.
    const nodeIds = new Set(nodeList.map((n) => n.id));
    const layoutEdges = edgeList.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    const positioned = layoutWithDagre(nodeList, layoutEdges);

    return { nodes: positioned, edges: edgeList };
  }, [data]);

  return (
    <div
      ref={fullscreenRef}
      className={`w-full ${isFullscreen ? "h-screen rounded-none border-0" : "h-[calc(100vh-120px)] rounded-lg border border-zinc-200 dark:border-zinc-700/40"} bg-white dark:bg-[#171719]`}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        // Layout is dagre-fixed; dragging just desynchronizes the visual
        // order from reality. Also disable the edge-drawing affordances --
        // this view is read-only. Pan/zoom on the canvas stay on.
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
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
        <MiniMap
          pannable
          zoomable
          className="!bg-white/80 dark:!bg-zinc-800/80 !border-zinc-200 dark:!border-zinc-700/40"
          nodeColor={(n) => {
            if (n.type === "org") return "rgb(16 185 129 / 0.6)";
            if (n.type === "team") return "rgb(161 161 170 / 0.7)";
            return "rgb(113 113 122 / 0.5)";
          }}
        />
      </ReactFlow>
    </div>
  );
}
