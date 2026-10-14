/**
 * Bridge visualisations built only from stored Audience Bridge Scores passed in by the caller.
 * Nothing is computed here except geometry: widths, positions and colour intensity follow the
 * given scores and confidence values. A score is a potential-bridge ranking signal, not observed
 * audience movement.
 */
import type { KeyboardEvent } from "react";

export interface BridgeTarget {
  id: string;
  label: string;
  score: number | null;
  confidence: number | null;
  rank: number | null;
}

/** Colour for a score in [0, 1]: light indigo (weak) to deep navy (strong). */
export function scoreColor(score: number | null): string {
  const t = Math.max(0, Math.min(1, score ?? 0));
  const a = [199, 210, 254], b = [30, 58, 138];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const fmt = (v: number | null, d = 3) => (v === null ? "—" : v.toFixed(d));
const onKey = (fn: () => void) => (e: KeyboardEvent) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); }
};

/** Ego network: the source in the centre, every scored destination around it, directed edges for the
 * top `depth` destinations (width and colour follow the score). */
export function EgoNetwork({ source, targets, depth, selected, onSelect }: {
  source: { id: string; label: string };
  targets: BridgeTarget[];
  depth: number;
  selected?: string;
  onSelect?: (id: string) => void;
}) {
  const S = 720, C = S / 2, R = 200;
  const ordered = [...targets].sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9));
  const shown = new Set(ordered.slice(0, depth).map((t) => t.id));
  const pos = new Map(ordered.map((t, i) => {
    const a = (2 * Math.PI * i) / Math.max(1, ordered.length) - Math.PI / 2;
    return [t.id, { a, x: C + R * Math.cos(a), y: C + R * Math.sin(a) }];
  }));
  const summary = `${source.label}: ${ordered.length} destinations; top ${Math.min(depth, ordered.length)} drawn as directed edges. `
    + ordered.slice(0, depth).map((t) => `${t.label} ${fmt(t.score)}`).join("; ");
  return (
    <figure className="ego" aria-label={summary}>
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-hidden="true">
        <defs>
          <marker id="ego-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="14" markerHeight="14" markerUnits="userSpaceOnUse" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="context-stroke" />
          </marker>
        </defs>
        <circle cx={C} cy={C} r={R} className="ego__orbit" />
        {ordered.filter((t) => shown.has(t.id)).reverse().map((t) => {
          const p = pos.get(t.id)!;
          const on = selected === t.id;
          const ex = C + (R - 16) * Math.cos(p.a), ey = C + (R - 16) * Math.sin(p.a);
          const sx0 = C + 34 * Math.cos(p.a), sy0 = C + 34 * Math.sin(p.a);
          return (
            <line key={`e${t.id}`} x1={sx0} y1={sy0} x2={ex} y2={ey} markerEnd="url(#ego-arrow)"
              stroke={on ? "var(--viz-highlight)" : scoreColor(t.score)} strokeWidth={1.5 + 9 * Math.max(0, t.score ?? 0)}
              strokeOpacity={on ? 1 : 0.85} strokeLinecap="round" />
          );
        })}
        <circle cx={C} cy={C} r={32} className="ego__source" />
        <text x={C} y={C + 4} textAnchor="middle" className="ego__source-label">SOURCE</text>
        {ordered.map((t) => {
          const p = pos.get(t.id)!;
          const on = selected === t.id;
          // radial labels: rotated along the spoke, flipped on the left half so text stays upright
          const left = Math.cos(p.a) < -1e-6;
          const deg = (p.a * 180) / Math.PI + (left ? 180 : 0);
          const lx = C + (R + 18) * Math.cos(p.a), ly = C + (R + 18) * Math.sin(p.a);
          return (
            <g key={t.id} className={`ego__node${on ? " is-on" : ""}${shown.has(t.id) ? "" : " is-faint"}`} role="button" tabIndex={0}
              aria-pressed={on} aria-label={`${t.label}: rank ${t.rank ?? "—"}, score ${fmt(t.score)}`}
              onClick={() => onSelect?.(t.id)} onKeyDown={onKey(() => onSelect?.(t.id))}>
              <circle cx={p.x} cy={p.y} r={18} className="ego__hit" />
              <circle cx={p.x} cy={p.y} r={on ? 11 : 8} fill={on ? "var(--viz-highlight)" : scoreColor(t.score)} className="ego__dot" />
              <text x={lx} y={ly} dy="0.35em" textAnchor={left ? "end" : "start"} transform={`rotate(${deg} ${lx} ${ly})`} className="ego__label">{short(t.label, 18)}</text>
              <title>{`#${t.rank ?? "—"} ${t.label}: ${fmt(t.score)}`}</title>
            </g>
          );
        })}
      </svg>
      <figcaption className="ego__caption">
        <span className="ego__scale"><i style={{ background: scoreColor(0.1) }} /> weaker</span>
        <span className="ego__scale"><i style={{ background: scoreColor(0.9) }} /> stronger score</span>
        <span>Edges: top {Math.min(depth, ordered.length)} of {ordered.length} destinations</span>
      </figcaption>
    </figure>
  );
}
