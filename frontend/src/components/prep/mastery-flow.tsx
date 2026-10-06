"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type {
  MasteryGraph,
  MasteryState,
} from "@/features/prep/sample-mastery";
import { MASTERY_COLORS } from "@/components/prep/status-chip";

/** Data carried by each custom mastery node. */
type MasteryNodeData = {
  label: string;
  state: MasteryState;
  statusLabel: string;
};
type MasteryFlowNode = Node<MasteryNodeData, "mastery">;

/**
 * Read-only mastery node, styled with the shared `MASTERY_COLORS` palette so it
 * matches the study-plan chips exactly. Handles are present (so prerequisite
 * edges connect) but rendered nearly invisible to keep the editorial calm.
 */
function MasteryNodeComponent({ data }: NodeProps<MasteryFlowNode>) {
  const c = MASTERY_COLORS[data.state];
  return (
    <div
      className="rounded-[10px] border px-3.5 py-2.5 text-center"
      style={{
        backgroundColor: c.bg,
        borderColor: c.border,
        minWidth: 150,
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ opacity: 0, width: 1, height: 1, border: "none" }}
        isConnectable={false}
      />
      <p
        className="text-[13px] font-medium"
        style={{ color: "var(--color-ink)" }}
      >
        {data.label}
      </p>
      <p
        className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.1em]"
        style={{ color: c.fg }}
      >
        {data.statusLabel}
      </p>
      <Handle
        type="source"
        position={Position.Right}
        style={{ opacity: 0, width: 1, height: 1, border: "none" }}
        isConnectable={false}
      />
    </div>
  );
}

// Module-level constant — defining nodeTypes inline would remount on every
// render and trip a React Flow warning.
const NODE_TYPES: NodeTypes = { mastery: MasteryNodeComponent };

function toFlow(
  graph: MasteryGraph,
  labels: Record<MasteryState, string>,
): {
  nodes: MasteryFlowNode[];
  edges: Edge[];
} {
  const nodes: MasteryFlowNode[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "mastery",
    position: { x: n.x, y: n.y },
    data: { label: n.label, state: n.state, statusLabel: labels[n.state] },
    draggable: false,
    selectable: false,
    connectable: false,
  }));

  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    style: { stroke: "var(--color-faint)", strokeWidth: 1.5 },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: "var(--color-faint)",
      width: 16,
      height: 16,
    },
  }));

  return { nodes, edges };
}

export function MasteryFlow({
  graph,
  labels,
}: {
  graph: MasteryGraph;
  labels: Record<MasteryState, string>;
}) {
  const { nodes, edges } = useMemo(
    () => toFlow(graph, labels),
    [graph, labels],
  );
  return (
    <ReactFlow
      colorMode="dark"
      style={{ background: "var(--color-panel)", fontFamily: "inherit" }}
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      nodesFocusable={false}
      edgesFocusable={false}
      elementsSelectable={false}
      panOnDrag={false}
      zoomOnScroll={false}
      zoomOnPinch={false}
      zoomOnDoubleClick={false}
      preventScrolling={false}
      minZoom={0.4}
      maxZoom={1.2}
    >
      <Background color="var(--color-line)" gap={22} size={1.2} />
    </ReactFlow>
  );
}
