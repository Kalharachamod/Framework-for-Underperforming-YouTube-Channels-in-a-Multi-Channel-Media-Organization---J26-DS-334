/**
 * Card graph: HTML cards placed on a virtual canvas, connected by SVG edges, scaled to fit the
 * container (zoom with the buttons or Ctrl + wheel / pinch). Purely presentational: positions, labels
 * and values come from the caller. Cards are buttons when `onSelect` is given (keyboard accessible).
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

export interface FlowNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  content: ReactNode;
  label: string; // accessible name
  tone?: "ok" | "stored" | "missing" | "failed" | "neutral" | "accent";
  selected?: boolean;
}

export interface FlowEdge {
  from: string;
  to: string;
  dashed?: boolean;
  width?: number;
  color?: string;
  label?: string;
  /** where the edge leaves/enters: vertical flow (bottom → top) or horizontal (right → left) */
  dir?: "down" | "right";
  muted?: boolean;
  /** position of the label along a vertical edge (0 = start, 1 = end); default 0.7 */
  labelAt?: number;
}

export interface FlowLane {
  id: string;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export function FlowCanvas({ width, height, nodes, edges, lanes = [], onSelect, label, minScale = 0.45 }: {
  width: number;
  height: number;
  nodes: FlowNode[];
  edges: FlowEdge[];
  lanes?: FlowLane[];
  onSelect?: (id: string) => void;
  label: string;
  minScale?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState(width);
  const [zoom, setZoom] = useState(1);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setBox(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const fit = Math.max(minScale, Math.min(1, box / width));
  const scale = fit * zoom;
  const pos = new Map(nodes.map((n) => [n.id, n]));
  useEffect(() => {
    // native, non-passive listener so Ctrl + wheel (and trackpad pinch) zooms the graph, not the page
    const el = ref.current;
    if (!el) return undefined;
    const onWheel = (e: globalThis.WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setZoom((z) => Math.min(2, Math.max(0.5, z * (e.deltaY < 0 ? 1.1 : 0.9))));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <div className="flow" aria-label={label} role="group">
      <div className="flow__tools">
        <span className="flow__hint">Ctrl + scroll or pinch to zoom · click a card for details</span>
        <button type="button" onClick={() => setZoom((z) => Math.max(0.5, z * 0.85))} aria-label="Zoom out">−</button>
        <button type="button" onClick={() => setZoom(1)} aria-label="Fit to width">Fit</button>
        <button type="button" onClick={() => setZoom((z) => Math.min(2, z * 1.15))} aria-label="Zoom in">+</button>
      </div>
      <div className="flow__viewport" ref={ref}>
        <div className="flow__sizer" style={{ width: width * scale, height: height * scale }}>
          <div className="flow__canvas" style={{ width, height, transform: `scale(${scale})` }}>
            {lanes.map((l) => (
              <div key={l.id} className="flow__lane" style={{ left: l.x, top: l.y, width: l.w, height: l.h }}>
                <span className="flow__lane-title">{l.title}</span>
              </div>
            ))}
            <svg className="flow__edges" width={width} height={height} aria-hidden="true">
              <defs>
                <marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto">
                  <path d="M0,1 L10,5 L0,9 z" fill="#64748b" />
                </marker>
              </defs>
              {edges.map((e) => {
                const a = pos.get(e.from), b = pos.get(e.to);
                if (!a || !b) return null;
                let d: string, lx: number, ly: number;
                if (e.dir === "right") {
                  const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x - 4, y2 = b.y + b.h / 2, mx = (x1 + x2) / 2;
                  d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
                  const t = e.labelAt ?? 0.5;
                  lx = x1 + (x2 - x1) * t; ly = y1 + (y2 - y1) * t;
                } else {
                  const x1 = a.x + a.w / 2, y1 = a.y + a.h, x2 = b.x + b.w / 2, y2 = b.y - 4, my = (y1 + y2) / 2;
                  d = `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`;
                  // label at 70% along the curve, where neighbouring edges have already fanned out
                  const t = e.labelAt ?? 0.7, u = 1 - t;
                  lx = u * u * u * x1 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x2;
                  ly = u * u * u * y1 + 3 * u * u * t * my + 3 * u * t * t * my + t * t * t * y2;
                }
                return (
                  <g key={`${e.from}-${e.to}`} className={e.muted ? "flow__edge is-muted" : "flow__edge"}>
                    <path d={d} fill="none" stroke={e.color ?? "#64748b"} strokeWidth={e.width ?? 1.5}
                      strokeDasharray={e.dashed ? "5 5" : undefined} markerEnd="url(#flow-arrow)" strokeLinecap="round" />
                    {e.label && (
                      <g transform={`translate(${lx}, ${ly})`}>
                        <rect x={-Math.max(24, e.label.length * 3.4 + 9)} y={-10} width={Math.max(48, e.label.length * 6.8 + 18)} height={20} rx={10} className="flow__edge-pill" />
                        <text textAnchor="middle" y={4} className="flow__edge-label">{e.label}</text>
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>
            {nodes.map((n) => {
              const cls = `flow__card tone-${n.tone ?? "neutral"}${n.selected ? " is-selected" : ""}`;
              const style = { left: n.x, top: n.y, width: n.w, height: n.h };
              return onSelect ? (
                <button key={n.id} type="button" className={cls} style={style} aria-label={n.label} aria-pressed={!!n.selected} onClick={() => onSelect(n.id)}>
                  {n.content}
                </button>
              ) : (
                <div key={n.id} className={cls} style={style} aria-label={n.label}>{n.content}</div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Legend row for card graphs. */
export function FlowLegend({ items }: { items: { kind: "dot" | "line" | "dash"; tone?: string; label: string }[] }) {
  return (
    <ul className="flow-legend">
      {items.map((i) => (
        <li key={i.label}>
          {i.kind === "dot" ? <i className={`flow-legend__dot tone-${i.tone}`} /> : <i className={`flow-legend__line${i.kind === "dash" ? " is-dash" : ""}`} />}
          {i.label}
        </li>
      ))}
    </ul>
  );
}
