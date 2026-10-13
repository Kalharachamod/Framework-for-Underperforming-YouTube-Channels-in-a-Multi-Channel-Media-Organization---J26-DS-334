/**
 * Bridge tree: a source channel card connected to its top-ranked destination cards. Edge width,
 * colour and label follow the stored Audience Bridge Score; nothing is computed except layout.
 */
import { scoreColor, type BridgeTarget } from "./BridgeViz";
import { FlowCanvas, FlowLegend, type FlowEdge, type FlowNode } from "./FlowCanvas";

export interface TreeTarget extends BridgeTarget {
  shared: number | null;
}

const W = 900, PER_ROW = 5, CARD_W = 162, CARD_H = 112, TOP = 20, SRC_H = 90, ROW_GAP = 70, FIRST_ROW = TOP + SRC_H + 120;
const fmt = (v: number | null, d = 3) => (v === null ? "—" : v.toFixed(d));

export function BridgeTree({ source, targets, selected, onSelect, subtitle }: {
  source: { id: string; label: string };
  targets: TreeTarget[];
  selected?: string;
  onSelect?: (id: string) => void;
  subtitle?: string;
}) {
  const rows = Math.max(1, Math.ceil(targets.length / PER_ROW));
  const height = FIRST_ROW + rows * CARD_H + (rows - 1) * ROW_GAP + 24;
  const srcW = 280;
  const nodes: FlowNode[] = [{
    id: `src:${source.id}`, x: (W - srcW) / 2, y: TOP, w: srcW, h: SRC_H, tone: "accent", label: `Source channel ${source.label}`,
    content: (
      <span className="fc">
        <span className="fc__head"><span className="fc__icon fc__icon--source">S</span><span className="fc__title">{source.label}</span></span>
        <span className="fc__sub">Source channel</span>
        <span className="fc__meta">{subtitle ?? `${targets.length} destinations shown`}</span>
      </span>
    ),
  }];
  const edges: FlowEdge[] = [];
  targets.forEach((t, i) => {
    const row = Math.floor(i / PER_ROW), inRow = Math.min(PER_ROW, targets.length - row * PER_ROW), col = i % PER_ROW;
    const gap = (W - inRow * CARD_W) / (inRow + 1);
    const x = gap + col * (CARD_W + gap), y = FIRST_ROW + row * (CARD_H + ROW_GAP);
    const on = selected === t.id;
    nodes.push({
      id: t.id, x, y, w: CARD_W, h: CARD_H, tone: on ? "accent" : "stored", selected: on,
      label: `${t.label}: rank ${t.rank ?? "—"}, score ${fmt(t.score)}, confidence ${fmt(t.confidence, 2)}`,
      content: (
        <span className="fc">
          <span className="fc__head"><span className="fc__rank">#{t.rank ?? "—"}</span><span className="fc__title">{t.label}</span></span>
          <span className="fc__chips fc__chips--stack">
            <span className="fc__chip"><b>score</b> {fmt(t.score)}</span>
            <span className="fc__chip"><b>conf</b> {fmt(t.confidence, 2)}</span>
            <span className="fc__chip"><b>shared</b> {t.shared ?? "—"}</span>
          </span>
        </span>
      ),
    });
    edges.push({ from: `src:${source.id}`, to: t.id, width: 1.5 + 7 * Math.max(0, t.score ?? 0),
      color: on ? "var(--viz-highlight)" : scoreColor(t.score), label: fmt(t.score) });
  });
  return (
    <>
      <FlowCanvas width={W} height={height} nodes={nodes} edges={edges} label={`${source.label} and its top ${targets.length} potential audience bridges`}
        onSelect={(id) => { if (!id.startsWith("src:")) onSelect?.(id); }} />
      <FlowLegend items={[
        { kind: "line", label: "Line width and colour follow the stored score" },
        { kind: "dot", tone: "accent", label: "Selected" },
      ]} />
    </>
  );
}
